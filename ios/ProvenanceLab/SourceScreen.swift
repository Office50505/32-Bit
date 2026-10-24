import PhotosUI
import SwiftUI
import UIKit
import UniformTypeIdentifiers

struct SourceScreen: View {
    @EnvironmentObject private var model: AppModel
    @State private var showsFileImporter = false
    @State private var photoItem: PhotosPickerItem?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Start with your source")
                        .font(.largeTitle.weight(.light))
                        .foregroundStyle(PLTheme.ink)
                    Text("Attach the original record, confirm the structure, then keep every validation decision reproducible.")
                        .font(.subheadline)
                        .foregroundStyle(PLTheme.muted)
                }

                MoleculeOrb()
                    .frame(maxWidth: .infinity)

                Picker("Source type", selection: $model.sourceKind) {
                    ForEach(SourceKind.allCases) { kind in Text(kind.rawValue).tag(kind) }
                }
                .pickerStyle(.segmented)
                .onChange(of: model.sourceKind) { _, kind in
                    if kind == .smiles { model.importedSource = nil }
                }

                if model.sourceKind != .smiles {
                    sourceImporter
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Molecular structure")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(PLTheme.muted)
                    TextField("Optional molecule label", text: $model.draftLabel)
                        .textFieldStyle(.roundedBorder)
                    TextEditor(text: $model.draftSmiles)
                        .font(.body.monospaced())
                        .frame(minHeight: 116)
                        .padding(8)
                        .scrollContentBackground(.hidden)
                        .background(Color(.secondarySystemBackground), in: .rect(cornerRadius: 12))
                        .overlay {
                            RoundedRectangle(cornerRadius: 12).stroke(PLTheme.border)
                        }
                    if model.sourceKind == .paper {
                        TextField("Page (optional)", text: $model.draftPage)
                            .keyboardType(.numberPad)
                            .textFieldStyle(.roundedBorder)
                    }
                }

                Button {
                    Task { await model.reviewDraft() }
                } label: {
                    Label("Review candidate", systemImage: "arrow.right")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(model.draftSmiles.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                workflow
            }
            .padding()
        }
        .background(PLTheme.background)
        .navigationTitle("New Analysis")
        .navigationBarTitleDisplayMode(.inline)
        .fileImporter(
            isPresented: $showsFileImporter,
            allowedContentTypes: allowedTypes,
            allowsMultipleSelection: false
        ) { result in
            guard case .success(let urls) = result, let url = urls.first else {
                if case .failure(let error) = result { model.errorMessage = error.localizedDescription }
                return
            }
            Task { await model.importFile(from: url, as: model.sourceKind) }
        }
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            Task {
                do {
                    guard let data = try await item.loadTransferable(type: Data.self) else { return }
                    guard let image = UIImage(data: data), let jpeg = image.jpegData(compressionQuality: 0.92) else {
                        throw APIClientError.transport("The selected photo could not be converted to JPEG.")
                    }
                    try await model.importData(jpeg, filename: "photo-\(UUID().uuidString).jpg", as: .photo)
                } catch { model.errorMessage = error.localizedDescription }
            }
        }
        .sheet(item: $model.preview) { preview in
            CandidateConfirmationView(preview: preview)
                .presentationDetents([.large])
        }
    }

    @ViewBuilder
    private var sourceImporter: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let source = model.importedSource, source.kind == model.sourceKind {
                HStack(spacing: 12) {
                    Image(systemName: "doc.badge.checkmark")
                        .font(.title2)
                        .foregroundStyle(PLTheme.verified)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(source.filename).font(.subheadline.weight(.semibold)).lineLimit(1)
                        Text("SHA-256  \(source.sha256.prefix(14))…")
                            .font(.caption2.monospaced())
                            .foregroundStyle(PLTheme.muted)
                    }
                    Spacer()
                    Button("Remove", systemImage: "xmark.circle.fill") { model.importedSource = nil }
                        .labelStyle(.iconOnly)
                }
                .padding()
                .background(Color(.systemBackground), in: .rect(cornerRadius: 14))
                .overlay { RoundedRectangle(cornerRadius: 14).stroke(PLTheme.border) }
            }

            if model.sourceKind == .photo {
                HStack {
                    PhotosPicker(selection: $photoItem, matching: .images) {
                        Label("Photo Library", systemImage: "photo.on.rectangle")
                    }
                    .buttonStyle(.bordered)
                    Button("Browse Files", systemImage: "folder") { showsFileImporter = true }
                        .buttonStyle(.bordered)
                }
            } else {
                Button {
                    showsFileImporter = true
                } label: {
                    Label("Choose \(model.sourceKind.rawValue)", systemImage: model.sourceKind == .csv ? "tablecells" : "doc")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }
            Text(model.sourceKind == .photo
                 ? "PNG, JPEG, or WebP · MolNexTR extracts a candidate · 5 MB max"
                 : model.sourceKind == .csv
                    ? "UTF-8 CSV with a SMILES or structure column · 5 MB max"
                    : "Attach the PDF, then transcribe the SMILES exactly · 5 MB max")
                .font(.caption)
                .foregroundStyle(PLTheme.muted)
        }
    }

    private var workflow: some View {
        VStack(alignment: .leading, spacing: 15) {
            Text("A careful path from source to result")
                .font(.title3.weight(.semibold))
            workflowRow("1", "Add a source", "SMILES, PDF, molecular image, or CSV")
            workflowRow("2", "Confirm the structure", "Compare the candidate before it enters the run")
            workflowRow("3", "Validate and compare", "Keep computation, evidence, and provenance separate")
        }
        .padding(.top, 10)
    }

    private func workflowRow(_ number: String, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Text(number).font(.caption.monospaced().weight(.bold)).foregroundStyle(PLTheme.blue)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(PLTheme.muted)
            }
        }
    }

    private var allowedTypes: [UTType] {
        switch model.sourceKind {
        case .paper: [.pdf]
        case .csv: [.commaSeparatedText, .plainText]
        case .photo: [.png, .jpeg, .webP]
        case .smiles: [.plainText]
        }
    }
}
private struct CandidateConfirmationView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var model: AppModel
    var preview: AnalyzeResponse

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(preview.label).font(.title2.weight(.semibold))
                            Text(preview.rawInput).font(.caption.monospaced()).foregroundStyle(PLTheme.muted)
                        }
                        Spacer()
                        StatusPill(status: preview.status)
                    }
                    if let svg = preview.depictionSvg {
                        SVGView(svg: svg).frame(height: 250)
                    }
                    if let issue = preview.issues.first {
                        Label(issue.explanation, systemImage: "exclamationmark.triangle")
                            .font(.subheadline)
                            .foregroundStyle(issue.severity == "error" ? PLTheme.invalid : PLTheme.ambiguous)
                            .padding()
                            .background(Color(.secondarySystemBackground), in: .rect(cornerRadius: 12))
                    }
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(preview.properties.prefix(4)) { property in
                            LabeledContent(property.label, value: property.computed.displayText)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Confirm Candidate")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Edit", systemImage: "pencil") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Confirm", systemImage: "checkmark") {
                        dismiss()
                        Task { await model.confirmPreview() }
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
    }
}
