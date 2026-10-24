import SwiftUI

struct RootView: View {
    @EnvironmentObject private var model: AppModel
    @State private var showsBenzo = false
    @State private var showsSettings = false

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            TabView(selection: $model.activeTab) {
                NavigationStack { SourceScreen() }
                    .tabItem { Label("Source", systemImage: "plus.circle") }
                    .tag(AppTab.source)

                NavigationStack { ValidationScreen() }
                    .tabItem { Label("Validate", systemImage: "checkmark.seal") }
                    .badge(model.results.count)
                    .tag(AppTab.validate)

                NavigationStack { CompareScreen() }
                    .tabItem { Label("Compare", systemImage: "tablecells") }
                    .tag(AppTab.compare)

                NavigationStack { ReportScreen() }
                    .tabItem { Label("Report", systemImage: "doc.richtext") }
                    .tag(AppTab.report)
            }

            Button {
                showsBenzo = true
            } label: {
                Image(systemName: "atom")
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(.white)
                    .frame(width: 54, height: 54)
                    .background(PLTheme.spectrum, in: .circle)
                    .shadow(color: PLTheme.blue.opacity(0.28), radius: 16, y: 8)
            }
            .accessibilityLabel("Ask Benzo")
            .padding(.trailing, 18)
            .padding(.bottom, 76)
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            HStack(spacing: 10) {
                BrandMark(size: 32)
                Text("Provenance") + Text("Lab").foregroundStyle(PLTheme.blue)
                Spacer()
                Button("Server", systemImage: "server.rack") { showsSettings = true }
                    .labelStyle(.iconOnly)
            }
            .font(.headline)
            .foregroundStyle(PLTheme.ink)
            .padding(.horizontal)
            .padding(.vertical, 9)
            .background(.bar)
        }
        .sheet(isPresented: $showsBenzo) { BenzoSheet() }
        .sheet(isPresented: $showsSettings) { ServerSettingsView() }
        .alert(
            "ProvenanceLab",
            isPresented: Binding(
                get: { model.errorMessage != nil },
                set: { if !$0 { model.errorMessage = nil } }
            )
        ) {
            Button("OK", role: .cancel) { model.errorMessage = nil }
        } message: {
            Text(model.errorMessage ?? "Unknown error")
        }
        .overlay {
            if model.isBusy { LoadingOverlay(message: model.busyMessage) }
        }
        .animation(.easeInOut(duration: 0.2), value: model.isBusy)
    }
}
private struct ServerSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            Form {
                Section("API server") {
                    TextField("https://api.example.com", text: $model.serverURLText)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                } footer: {
                    Text("Use http://127.0.0.1:8000 in Simulator. A physical iPhone needs your Mac's LAN address or a production HTTPS URL.")
                }
                Section("Privacy") {
                    Label("Molecular questions are sent to your configured backend.", systemImage: "lock.shield")
                    Label("Source files stay on-device except images submitted to MolNexTR.", systemImage: "iphone")
                }
            }
            .navigationTitle("Server Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close", systemImage: "xmark") { dismiss() }.labelStyle(.iconOnly)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save", systemImage: "checkmark") {
                        Task { await model.saveServerURL(); dismiss() }
                    }
                    .labelStyle(.iconOnly)
                    .buttonStyle(.borderedProminent)
                }
            }
        }
    }
}
