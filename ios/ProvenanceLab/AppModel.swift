import Combine
import CryptoKit
import Foundation
import UniformTypeIdentifiers

@MainActor
final class AppModel: ObservableObject {
    @Published var activeTab: AppTab = .source
    @Published var sourceKind: SourceKind = .smiles
    @Published var draftLabel = ""
    @Published var draftSmiles = ""
    @Published var draftPage = ""
    @Published var importedSource: ImportedSource?
    @Published var preview: AnalyzeResponse?
    @Published var run: RunResponse?
    @Published var runInputs: [AnalyzeRequest] = []
    @Published var selectedResultID: String?
    @Published var isBusy = false
    @Published var busyMessage = ""
    @Published var errorMessage: String?
    @Published var reportURL: URL?
    @Published var serverURLText: String

    private var editingIndex: Int?
    private var preservedSourceMetadata: SourceMetadata?
    private var client: APIClient

    private static let serverKey = "ProvenanceLab.serverURL"
    private static let runKey = "ProvenanceLab.latestRun"
    private static let inputsKey = "ProvenanceLab.latestRunInputs"

    init() {
        let configured = UserDefaults.standard.string(forKey: Self.serverKey)
            ?? "http://127.0.0.1:8000"
        serverURLText = configured
        client = APIClient(baseURL: URL(string: configured) ?? URL(string: "http://127.0.0.1:8000")!)
        restoreLatestRun()
    }

    var results: [AnalyzeResponse] { run?.results ?? [] }

    var selectedResult: AnalyzeResponse? {
        results.first(where: { $0.id == selectedResultID }) ?? results.first
    }

    var currentSmiles: String? {
        let draft = draftSmiles.trimmingCharacters(in: .whitespacesAndNewlines)
        return draft.isEmpty ? selectedResult?.canonicalSmiles ?? selectedResult?.rawInput : draft
    }

    func saveServerURL() async {
        let normalized = serverURLText.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: normalized), let scheme = url.scheme, ["http", "https"].contains(scheme) else {
            errorMessage = APIClientError.invalidServerURL.localizedDescription
            return
        }
        serverURLText = normalized
        UserDefaults.standard.set(normalized, forKey: Self.serverKey)
        await client.updateBaseURL(url)
    }

    func resetDraft() {
        sourceKind = .smiles
        draftLabel = ""
        draftSmiles = ""
        draftPage = ""
        importedSource = nil
        preview = nil
        editingIndex = nil
        preservedSourceMetadata = nil
        errorMessage = nil
    }

    func importFile(from url: URL, as kind: SourceKind) async {
        let accessed = url.startAccessingSecurityScopedResource()
        defer { if accessed { url.stopAccessingSecurityScopedResource() } }
        do {
            let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
            guard size <= 5 * 1_024 * 1_024 else {
                throw APIClientError.transport("Choose a source smaller than 5 MB.")
            }
            let data = try Data(contentsOf: url, options: .mappedIfSafe)
            try await importData(data, filename: url.lastPathComponent, as: kind)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func importData(_ data: Data, filename: String, as kind: SourceKind) async throws {
        guard data.count <= 5 * 1_024 * 1_024 else {
            throw APIClientError.transport("Choose a source smaller than 5 MB.")
        }
        let source = ImportedSource(
            kind: kind,
            filename: filename,
            mediaType: Self.mediaType(for: filename, kind: kind),
            data: data,
            sha256: SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(),
            extractionMethod: kind == .csv ? "csv-smiles-column" : kind == .paper
                ? "manual-smiles-transcription" : "MolNexTR-Graph-Recognizer"
        )
        sourceKind = kind
        importedSource = source
        preservedSourceMetadata = nil
        errorMessage = nil

        switch kind {
        case .csv:
            let parsed = try CSVParser.firstMolecule(in: data)
            draftSmiles = parsed.smiles
            if let label = parsed.label { draftLabel = label }
        case .photo:
            isBusy = true
            busyMessage = "Preparing molecular image recognition…"
            defer { isBusy = false; busyMessage = "" }
            _ = try await client.prepareExtractionEngine()
            busyMessage = "Reading molecular structure…"
            let extraction = try await client.extractImage(source)
            guard extraction.sourceSha256 == source.sha256 else {
                throw APIClientError.server(
                    code: "SOURCE_HASH_MISMATCH",
                    message: "The selected image changed during extraction."
                )
            }
            draftSmiles = extraction.candidateSmiles
            importedSource?.extractionMethod = "\(extraction.method) \(extraction.modelVersion)"
        case .paper, .smiles:
            break
        }
    }

    func reviewDraft() async {
        do {
            let request = try makeDraftRequest()
            isBusy = true
            busyMessage = "Running deterministic RDKit validation…"
            defer { isBusy = false; busyMessage = "" }
            preview = try await client.analyze(request)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func confirmPreview() async {
        do {
            let request = try makeDraftRequest()
            let nextInputs: [AnalyzeRequest]
            if let editingIndex {
                nextInputs = runInputs.enumerated().map { $0.offset == editingIndex ? request : $0.element }
            } else {
                nextInputs = runInputs + [request]
            }
            isBusy = true
            busyMessage = "Saving reproducible run…"
            defer { isBusy = false; busyMessage = "" }
            let nextRun = try await client.createRun(nextInputs)
            run = nextRun
            runInputs = nextInputs
            selectedResultID = nextRun.results[min(editingIndex ?? nextRun.results.count - 1, nextRun.results.count - 1)].id
            persistLatestRun()
            resetDraft()
            activeTab = .validate
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func edit(_ result: AnalyzeResponse) {
        guard let index = results.firstIndex(where: { $0.id == result.id }), runInputs.indices.contains(index) else { return }
        let request = runInputs[index]
        editingIndex = index
        draftLabel = request.label ?? ""
        draftSmiles = request.structure
        draftPage = request.source?.page.map(String.init) ?? ""
        sourceKind = SourceKind.allCases.first(where: { $0.apiValue == request.source?.sourceType }) ?? .smiles
        importedSource = nil
        preservedSourceMetadata = request.source
        preview = nil
        activeTab = .source
    }

    func remove(_ result: AnalyzeResponse) async {
        guard let index = results.firstIndex(where: { $0.id == result.id }) else { return }
        let nextInputs = runInputs.enumerated().compactMap { $0.offset == index ? nil : $0.element }
        if nextInputs.isEmpty {
            run = nil
            runInputs = []
            selectedResultID = nil
            clearPersistedRun()
            activeTab = .source
            return
        }
        do {
            isBusy = true
            busyMessage = "Updating run…"
            defer { isBusy = false; busyMessage = "" }
            run = try await client.createRun(nextInputs)
            runInputs = nextInputs
            selectedResultID = run?.results[min(index, nextInputs.count - 1)].id
            persistLatestRun()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func downloadReport() async {
        guard let run else { return }
        do {
            reportURL = nil
            isBusy = true
            busyMessage = "Generating signed PDF report…"
            defer { isBusy = false; busyMessage = "" }
            reportURL = try await client.downloadReport(runID: run.runId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func askBenzo(_ question: String) async throws -> BenzoChatResponse {
        try await client.askBenzo(question: question, currentSmiles: currentSmiles)
    }

    private func makeDraftRequest() throws -> AnalyzeRequest {
        let structure = draftSmiles.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !structure.isEmpty else {
            throw APIClientError.transport("Enter a SMILES structure before review.")
        }
        let label = draftLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        if sourceKind == .smiles {
            return AnalyzeRequest(
                structure: structure,
                label: label.isEmpty ? nil : label,
                source: SourceMetadata(sourceType: SourceKind.smiles.apiValue)
            )
        }
        guard let importedSource, importedSource.kind == sourceKind else {
            if let preservedSourceMetadata, preservedSourceMetadata.sourceType == sourceKind.apiValue {
                return AnalyzeRequest(
                    structure: structure,
                    label: label.isEmpty ? nil : label,
                    source: preservedSourceMetadata
                )
            }
            throw APIClientError.transport("Attach the \(sourceKind.rawValue) source before review.")
        }
        return AnalyzeRequest(
            structure: structure,
            label: label.isEmpty ? nil : label,
            source: SourceMetadata(
                filename: importedSource.filename,
                sourceType: sourceKind.apiValue,
                page: sourceKind == .paper ? Int(draftPage) : nil,
                mediaType: importedSource.mediaType,
                fileSize: importedSource.data.count,
                fileSha256: importedSource.sha256,
                extractionMethod: importedSource.extractionMethod
            )
        )
    }

    private func persistLatestRun() {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        if let run, let data = try? encoder.encode(run) { UserDefaults.standard.set(data, forKey: Self.runKey) }
        if let data = try? encoder.encode(runInputs) { UserDefaults.standard.set(data, forKey: Self.inputsKey) }
    }

    private func restoreLatestRun() {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard
            let runData = UserDefaults.standard.data(forKey: Self.runKey),
            let inputsData = UserDefaults.standard.data(forKey: Self.inputsKey),
            let restoredRun = try? decoder.decode(RunResponse.self, from: runData),
            let restoredInputs = try? decoder.decode([AnalyzeRequest].self, from: inputsData)
        else { return }
        run = restoredRun
        runInputs = restoredInputs
        selectedResultID = restoredRun.results.first?.id
    }

    private func clearPersistedRun() {
        UserDefaults.standard.removeObject(forKey: Self.runKey)
        UserDefaults.standard.removeObject(forKey: Self.inputsKey)
    }

    private static func mediaType(for filename: String, kind: SourceKind) -> String {
        switch kind {
        case .paper: "application/pdf"
        case .csv: "text/csv"
        case .photo:
            switch URL(fileURLWithPath: filename).pathExtension.lowercased() {
            case "png": "image/png"
            case "webp": "image/webp"
            default: "image/jpeg"
            }
        case .smiles: "text/plain"
        }
    }
}

private enum CSVParser {
    struct Molecule { var label: String?; var smiles: String }

    static func firstMolecule(in data: Data) throws -> Molecule {
        guard let source = String(data: data, encoding: .utf8) else {
            throw APIClientError.transport("The CSV must use UTF-8 encoding.")
        }
        let rows = parseRows(source)
        guard rows.count > 1 else {
            throw APIClientError.transport("The CSV needs a header and at least one molecule.")
        }
        let headers = rows[0].map(normalize)
        let smilesNames: Set<String> = ["smiles", "canonicalsmiles", "isomericsmiles", "structure", "molecule", "molecularvalue"]
        let labelNames: Set<String> = ["label", "name", "compound", "compoundname", "moleculename"]
        guard let smilesIndex = headers.firstIndex(where: smilesNames.contains) else {
            throw APIClientError.transport("The CSV needs a SMILES or structure column.")
        }
        let labelIndex = headers.firstIndex(where: labelNames.contains)
        guard let row = rows.dropFirst().first(where: { $0.indices.contains(smilesIndex) && !$0[smilesIndex].trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else {
            throw APIClientError.transport("The CSV does not contain a molecular value.")
        }
        let label = labelIndex.flatMap { row.indices.contains($0) ? row[$0].trimmingCharacters(in: .whitespacesAndNewlines) : nil }
        return Molecule(label: label?.isEmpty == true ? nil : label, smiles: row[smilesIndex].trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private static func normalize(_ value: String) -> String {
        value.replacingOccurrences(of: "\u{FEFF}", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "[\\s_-]+", with: "", options: .regularExpression)
    }

    private static func parseRows(_ source: String) -> [[String]] {
        var rows: [[String]] = []
        var row: [String] = []
        var field = ""
        var quoted = false
        var index = source.startIndex
        while index < source.endIndex {
            let character = source[index]
            let next = source.index(after: index)
            if character == "\"" {
                if quoted, next < source.endIndex, source[next] == "\"" {
                    field.append("\"")
                    index = source.index(after: next)
                    continue
                }
                quoted.toggle()
            } else if character == ",", !quoted {
                row.append(field); field = ""
            } else if character.isNewline, !quoted {
                row.append(field); field = ""
                if row.contains(where: { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) { rows.append(row) }
                row = []
            } else {
                field.append(character)
            }
            index = next
        }
        row.append(field)
        if row.contains(where: { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) { rows.append(row) }
        return rows
    }
}
