import Foundation

enum AppTab: Hashable {
    case source, validate, compare, report
}

enum SourceKind: String, CaseIterable, Identifiable, Codable {
    case smiles = "SMILES"
    case photo = "Photo"
    case paper = "PDF"
    case csv = "CSV"

    var id: String { rawValue }
    var apiValue: String {
        switch self {
        case .smiles: "direct-smiles"
        case .photo: "photo"
        case .paper: "paper"
        case .csv: "csv"
        }
    }
}

enum MoleculeStatus: String, Codable {
    case valid, ambiguous, invalid
}

enum ResultStatus: String, Codable {
    case available = "AVAILABLE"
    case invalidInput = "INVALID_INPUT"
    case ambiguousInput = "AMBIGUOUS_INPUT"
    case notComputable = "NOT_COMPUTABLE"
    case notAvailable = "NOT_AVAILABLE"
    case notApplicable = "NOT_APPLICABLE"
    case noReferenceMatch = "NO_REFERENCE_MATCH"
    case outsideSnapshotCoverage = "OUTSIDE_SNAPSHOT_COVERAGE"
    case computationError = "COMPUTATION_ERROR"
    case conflictingEvidence = "CONFLICTING_EVIDENCE"
}

enum JSONValue: Codable, Hashable {
    case string(String)
    case number(Double)
    case bool(Bool)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(String.self) { self = .string(value); return }
        if let value = try? container.decode(Double.self) { self = .number(value); return }
        if let value = try? container.decode(Bool.self) { self = .bool(value); return }
        throw DecodingError.typeMismatch(
            JSONValue.self,
            .init(codingPath: decoder.codingPath, debugDescription: "Unsupported JSON scalar")
        )
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        }
    }

    var displayText: String {
        switch self {
        case .string(let value): value
        case .number(let value): value.formatted(.number.precision(.fractionLength(0...4)))
        case .bool(let value): value ? "Yes" : "No"
        }
    }
}

struct SourceMetadata: Codable, Hashable {
    var filename: String? = nil
    var sourceType: String? = nil
    var citation: String? = nil
    var page: Int? = nil
    var mediaType: String? = nil
    var fileSize: Int? = nil
    var fileSha256: String? = nil
    var extractionMethod: String? = nil
}

struct AnalyzeRequest: Codable, Hashable {
    var structure: String
    var inputType = "smiles"
    var label: String?
    var source: SourceMetadata?
}

struct IssueLocation: Codable, Hashable {
    var atomIndices: [Int]
    var bondIndices: [Int]
    var smilesStart: Int?
    var smilesEnd: Int?
}

struct ValidationIssue: Codable, Hashable, Identifiable {
    var code: String
    var subcode: String?
    var title: String
    var severity: String
    var summary: String
    var explanation: String
    var whyItMatters: String
    var nextStep: String
    var location: IssueLocation
    var technicalDetail: String?
    var id: String { "\(code)-\(subcode ?? "")-\(title)" }
}

struct StandardizationStep: Codable, Hashable, Identifiable {
    var code: String
    var label: String
    var beforeSmiles: String
    var afterSmiles: String
    var changed: Bool
    var status: String
    var reasonCode: String?
    var reason: String?
    var id: String { code }
}

struct PropertyObservation: Codable, Hashable {
    var value: JSONValue?
    var unit: String?
    var status: ResultStatus
    var reasonCode: String?
    var reason: String?

    var displayText: String {
        guard let value else { return reason ?? status.rawValue.replacingOccurrences(of: "_", with: " ") }
        return [value.displayText, unit].compactMap { $0 }.joined(separator: " ")
    }
}

struct PropertyComparison: Codable, Hashable, Identifiable {
    var key: String
    var label: String
    var computed: PropertyObservation
    var evidence: PropertyObservation
    var comparisonStatus: ResultStatus
    var id: String { key }
}

struct ToolVersions: Codable, Hashable {
    var pipeline: String
    var python: String
    var rdkit: String
    var ruleset: String
}

struct RunManifest: Codable, Hashable {
    var analysisId: String
    var inputSha256: String
    var configurationSha256: String
    var outputSha256: String
    var snapshotId: String
    var snapshotScope: String
    var toolVersions: ToolVersions
}

struct AnalyzeResponse: Codable, Hashable, Identifiable {
    var analysisId: String
    var label: String
    var rawInput: String
    var inputType: String
    var status: MoleculeStatus
    var canonicalSmiles: String?
    var standardizedSmiles: String?
    var depictionSvg: String?
    var issues: [ValidationIssue]
    var standardizationSteps: [StandardizationStep]
    var properties: [PropertyComparison]
    var source: SourceMetadata?
    var manifest: RunManifest
    var id: String { analysisId }
}

struct BatchAnalyzeRequest: Codable { var molecules: [AnalyzeRequest] }

struct RunResponse: Codable, Hashable {
    var runId: String
    var results: [AnalyzeResponse]
    var inputSha256: String
    var configurationSha256: String
    var outputSha256: String
}

struct APIErrorEnvelope: Codable {
    struct Item: Codable {
        var code: String
        var message: String
        var field: String?
    }
    var error: Item
}

struct ExtractionEngineStatus: Codable {
    var stage: String
    var engine: String
    var ready: Bool
    var message: String
    var bytesDownloaded: Int
    var bytesTotal: Int?
    var progressPercent: Double?
    var modelVersion: String
    var errorCode: String?
}

struct ImageExtractionResponse: Codable {
    var status: String
    var candidateSmiles: String
    var method: String
    var modelVersion: String
    var sourceSha256: String
    var filename: String
    var mediaType: String
    var warnings: [String]
}

struct BenzoStructureSuggestion: Codable, Hashable, Identifiable {
    var title: String
    var detail: String
    var smiles: String?
    var id: String { "\(title)-\(smiles ?? "")" }
}

struct BenzoChatRequest: Codable { var question: String; var currentSmiles: String? }

struct BenzoChatResponse: Codable, Hashable {
    var scope: String
    var answer: String
    var suggestions: [BenzoStructureSuggestion]
    var model: String
}

struct ImportedSource: Hashable {
    var kind: SourceKind
    var filename: String
    var mediaType: String
    var data: Data
    var sha256: String
    var extractionMethod: String
}

struct ChatMessage: Identifiable, Hashable {
    enum Role: Hashable { case user, assistant, error }
    let id = UUID()
    var role: Role
    var text: String
    var suggestions: [BenzoStructureSuggestion] = []
}
