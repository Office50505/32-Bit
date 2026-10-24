import SwiftUI

struct ValidationScreen: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            if model.results.isEmpty {
                ContentUnavailableView {
                    Label("No analyzed structures", systemImage: "atom")
                } description: {
                    Text("Add a molecular source to create the first reproducible run.")
                } actions: {
                    Button("Add source") { model.activeTab = .source }
                        .buttonStyle(.borderedProminent)
                }
            } else {
                List(model.results) { result in
                    NavigationLink {
                        ValidationDetailView(result: result)
                    } label: {
                        ValidationRow(result: result)
                    }
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) {
                            Task { await model.remove(result) }
                        } label: {
                            Label("Remove", systemImage: "trash")
                        }
                    }
                    .swipeActions(edge: .leading) {
                        Button { model.edit(result) } label: {
                            Label("Edit", systemImage: "pencil")
                        }
                        .tint(PLTheme.blue)
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Validation complete")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Add source", systemImage: "plus") {
                    model.resetDraft()
                    model.activeTab = .source
                }
                .labelStyle(.iconOnly)
            }
        }
    }
}
private struct ValidationRow: View {
    var result: AnalyzeResponse

    var body: some View {
        HStack(spacing: 13) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(PLTheme.surfaceMuted)
                Image(systemName: "atom")
                    .font(.title2)
                    .foregroundStyle(PLTheme.blue)
            }
            .frame(width: 54, height: 54)
            VStack(alignment: .leading, spacing: 5) {
                Text(result.label).font(.headline)
                Text(result.canonicalSmiles ?? result.rawInput)
                    .font(.caption.monospaced())
                    .foregroundStyle(PLTheme.muted)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            StatusPill(status: result.status)
        }
        .padding(.vertical, 4)
    }
}

struct ValidationDetailView: View {
    @EnvironmentObject private var model: AppModel
    var result: AnalyzeResponse

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(result.label).font(.title.weight(.light))
                        Text(result.canonicalSmiles ?? result.rawInput)
                            .font(.caption.monospaced())
                            .foregroundStyle(PLTheme.muted)
                            .textSelection(.enabled)
                    }
                    Spacer()
                    StatusPill(status: result.status)
                }

                if let svg = result.depictionSvg {
                    SVGView(svg: svg)
                        .frame(height: 280)
                        .background(Color(.systemBackground), in: .rect(cornerRadius: 16))
                }

                section("Calculated properties", symbol: "function") {
                    ForEach(result.properties) { property in
                        HStack(alignment: .firstTextBaseline) {
                            Text(property.label).foregroundStyle(PLTheme.inkSoft)
                            Spacer()
                            Text(property.computed.displayText)
                                .font(.subheadline.monospaced())
                                .multilineTextAlignment(.trailing)
                        }
                        if property.id != result.properties.last?.id { Divider() }
                    }
                }

                section("Validation findings", symbol: "checkmark.shield") {
                    if result.issues.isEmpty {
                        Label("No blocking issue was detected.", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(PLTheme.verified)
                    } else {
                        ForEach(result.issues) { issue in
                            DisclosureGroup {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(issue.explanation)
                                    Text(issue.whyItMatters).foregroundStyle(PLTheme.muted)
                                    Label(issue.nextStep, systemImage: "arrow.right.circle")
                                }
                                .font(.subheadline)
                                .padding(.top, 6)
                            } label: {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(issue.title).font(.subheadline.weight(.semibold))
                                    Text(issue.code).font(.caption2.monospaced()).foregroundStyle(PLTheme.muted)
                                }
                            }
                        }
                    }
                }

                section("Standardization", symbol: "wand.and.stars") {
                    ForEach(result.standardizationSteps) { step in
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: step.changed ? "arrow.triangle.2.circlepath.circle.fill" : "checkmark.circle")
                                .foregroundStyle(step.changed ? PLTheme.blue : PLTheme.verified)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(step.label).font(.subheadline.weight(.semibold))
                                Text(step.afterSmiles).font(.caption.monospaced()).foregroundStyle(PLTheme.muted)
                            }
                        }
                    }
                }

                section("Provenance", symbol: "link.badge.plus") {
                    HashRow(label: "Input SHA-256", value: result.manifest.inputSha256)
                    Divider()
                    HashRow(label: "Output SHA-256", value: result.manifest.outputSha256)
                    Divider()
                    LabeledContent("RDKit", value: result.manifest.toolVersions.rdkit)
                    LabeledContent("Ruleset", value: result.manifest.toolVersions.ruleset)
                    LabeledContent("Snapshot", value: result.manifest.snapshotId)
                }
            }
            .padding()
        }
        .background(PLTheme.background)
        .navigationTitle("Structure detail")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { model.selectedResultID = result.id }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Edit", systemImage: "pencil") { model.edit(result) }
                    .labelStyle(.iconOnly)
            }
        }
    }

    private func section<Content: View>(
        _ title: String,
        symbol: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 13) {
            Label(title, systemImage: symbol).font(.headline).foregroundStyle(PLTheme.ink)
            content()
        }
        .padding()
        .background(Color(.systemBackground), in: .rect(cornerRadius: 16))
        .overlay { RoundedRectangle(cornerRadius: 16).stroke(PLTheme.border) }
    }
}

struct CompareScreen: View {
    @EnvironmentObject private var model: AppModel

    private var propertyKeys: [String] {
        Array(Set(model.results.flatMap { $0.properties.map(\.key) })).sorted()
    }

    var body: some View {
        Group {
            if model.results.count < 2 {
                ContentUnavailableView {
                    Label("Add another structure", systemImage: "tablecells")
                } description: {
                    Text("Comparison becomes available when a run contains at least two molecules.")
                } actions: {
                    Button("Add source") { model.resetDraft(); model.activeTab = .source }
                        .buttonStyle(.borderedProminent)
                }
            } else {
                ScrollView([.horizontal, .vertical]) {
                    Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 0) {
                        GridRow {
                            Text("Property").font(.caption.weight(.bold)).foregroundStyle(PLTheme.muted)
                                .frame(width: 150, alignment: .leading)
                            ForEach(model.results) { result in
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(result.label).font(.headline)
                                    StatusPill(status: result.status)
                                }
                                .frame(width: 180, alignment: .leading)
                            }
                        }
                        .padding(.vertical, 12)

                        Divider()

                        ForEach(propertyKeys, id: \.self) { key in
                            GridRow {
                                Text(propertyLabel(for: key))
                                    .font(.subheadline.weight(.semibold))
                                    .frame(width: 150, alignment: .leading)
                                ForEach(model.results) { result in
                                    Text(result.properties.first(where: { $0.key == key })?.computed.displayText ?? "Not available")
                                        .font(.caption.monospaced())
                                        .foregroundStyle(PLTheme.inkSoft)
                                        .frame(width: 180, alignment: .leading)
                                }
                            }
                            .padding(.vertical, 13)
                            Divider()
                        }
                    }
                    .padding()
                }
                .background(PLTheme.background)
            }
        }
        .navigationTitle("Compare")
    }

    private func propertyLabel(for key: String) -> String {
        model.results.lazy.compactMap { $0.properties.first(where: { $0.key == key })?.label }.first ?? key
    }
}

struct ReportScreen: View {
    @EnvironmentObject private var model: AppModel
    @State private var showsShare = false

    var body: some View {
        Group {
            if let run = model.run {
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 22).fill(PLTheme.ink)
                            VStack(spacing: 13) {
                                Image(systemName: "doc.text.magnifyingglass")
                                    .font(.system(size: 42, weight: .light))
                                    .foregroundStyle(PLTheme.cyan)
                                Text("Reproducible PDF report")
                                    .font(.title2.weight(.semibold))
                                    .foregroundStyle(.white)
                                Text("\(run.results.count) structures · backend-generated · hash verified")
                                    .font(.caption)
                                    .foregroundStyle(.white.opacity(0.68))
                            }
                            .padding(28)
                        }

                        VStack(alignment: .leading, spacing: 16) {
                            LabeledContent("Run ID", value: run.runId)
                            Divider()
                            HashRow(label: "Input SHA-256", value: run.inputSha256)
                            Divider()
                            HashRow(label: "Configuration SHA-256", value: run.configurationSha256)
                            Divider()
                            HashRow(label: "Output SHA-256", value: run.outputSha256)
                        }
                        .padding()
                        .background(Color(.systemBackground), in: .rect(cornerRadius: 16))
                        .overlay { RoundedRectangle(cornerRadius: 16).stroke(PLTheme.border) }

                        Text("The PDF is generated by the backend from the stored run. It includes validation findings, property states, standardization steps, and reproducibility hashes. Missing evidence remains explicitly missing.")
                            .font(.footnote)
                            .foregroundStyle(PLTheme.muted)

                        Button {
                            Task {
                                await model.downloadReport()
                                showsShare = model.reportURL != nil
                            }
                        } label: {
                            Label("Generate and share PDF", systemImage: "square.and.arrow.up")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                    }
                    .padding()
                }
                .background(PLTheme.background)
                .sheet(isPresented: $showsShare) {
                    if let url = model.reportURL { ActivityShareSheet(items: [url]) }
                }
            } else {
                ContentUnavailableView {
                    Label("No run to report", systemImage: "doc")
                } description: {
                    Text("Confirm at least one molecular source first.")
                } actions: {
                    Button("Start analysis") { model.activeTab = .source }
                        .buttonStyle(.borderedProminent)
                }
            }
        }
        .navigationTitle("Run report")
    }
}
