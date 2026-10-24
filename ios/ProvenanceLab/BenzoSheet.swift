import SwiftUI

struct BenzoSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var model: AppModel
    @FocusState private var composerFocused: Bool
    @State private var question = ""
    @State private var messages: [ChatMessage] = []
    @State private var isSending = false
    @State private var requestTask: Task<Void, Never>?

    private let prompts = [
        "What is the difference between L-alanine and D-alanine?",
        "What is the molecular formula of sulfuric acid?",
        "How do I fix an invalid bond order?",
        "Suggest a valid aromatic ring SMILES."
    ]

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            if messages.isEmpty { welcome }
                            ForEach(messages) { message in messageView(message) }
                            if isSending {
                                HStack(spacing: 10) {
                                    ProgressView().tint(PLTheme.cyan)
                                    Text("Benzo is checking project context…")
                                        .font(.caption)
                                        .foregroundStyle(PLTheme.muted)
                                    Spacer()
                                }
                                .id("thinking")
                            }
                        }
                        .padding()
                    }
                    .onChange(of: messages.count) { _, _ in
                        withAnimation(.easeOut(duration: 0.25)) { proxy.scrollTo(messages.last?.id, anchor: .bottom) }
                    }
                    .onChange(of: isSending) { _, sending in
                        if sending { withAnimation { proxy.scrollTo("thinking", anchor: .bottom) } }
                    }
                }

                Divider()
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Ask about bonds, SMILES, or this project", text: $question, axis: .vertical)
                        .lineLimit(1...5)
                        .focused($composerFocused)
                        .textFieldStyle(.plain)
                        .padding(11)
                        .background(Color(.secondarySystemBackground), in: .rect(cornerRadius: 14))
                        .onSubmit { submit() }
                    Button("Ask", systemImage: "arrow.up") { submit() }
                        .labelStyle(.iconOnly)
                        .buttonStyle(.borderedProminent)
                        .buttonBorderShape(.circle)
                        .controlSize(.large)
                        .disabled(question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
                }
                .padding()

                Label("Project-scoped guidance. Validate suggested structures before use.", systemImage: "checkmark.shield")
                    .font(.caption2)
                    .foregroundStyle(PLTheme.muted)
                    .padding(.bottom, 10)
            }
            .navigationTitle("Ask Benzo")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close", systemImage: "xmark") { dismiss() }.labelStyle(.iconOnly)
                }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .onDisappear { requestTask?.cancel() }
    }

    private var welcome: some View {
        VStack(spacing: 16) {
            MoleculeOrb().scaleEffect(0.55).frame(height: 112)
            Text("Molecular guidance, grounded in your current workspace.")
                .font(.headline)
                .multilineTextAlignment(.center)
            if let smiles = model.currentSmiles {
                Text(smiles)
                    .font(.caption.monospaced())
                    .foregroundStyle(PLTheme.blue)
                    .lineLimit(2)
            }
            VStack(spacing: 8) {
                ForEach(prompts, id: \.self) { prompt in
                    Button {
                        question = prompt
                        submit()
                    } label: {
                        HStack {
                            Text(prompt).multilineTextAlignment(.leading)
                            Spacer()
                            Image(systemName: "arrow.up.right")
                        }
                        .font(.subheadline)
                        .padding(11)
                    }
                    .buttonStyle(.plain)
                    .background(PLTheme.surfaceMuted, in: .rect(cornerRadius: 12))
                    .overlay { RoundedRectangle(cornerRadius: 12).stroke(PLTheme.border) }
                }
            }
        }
    }

    @ViewBuilder
    private func messageView(_ message: ChatMessage) -> some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 8) {
            Text(message.text)
                .font(.subheadline)
                .foregroundStyle(message.role == .user ? .white : message.role == .error ? PLTheme.invalid : PLTheme.ink)
                .padding(12)
                .background(
                    message.role == .user ? AnyShapeStyle(PLTheme.spectrum) : AnyShapeStyle(Color(.secondarySystemBackground)),
                    in: .rect(cornerRadius: 14)
                )
            ForEach(message.suggestions) { suggestion in
                VStack(alignment: .leading, spacing: 5) {
                    Text(suggestion.title).font(.caption.weight(.bold))
                    Text(suggestion.detail).font(.caption).foregroundStyle(PLTheme.muted)
                    if let smiles = suggestion.smiles {
                        Text(smiles).font(.caption2.monospaced()).foregroundStyle(PLTheme.blue).textSelection(.enabled)
                    }
                }
                .padding(10)
                .background(PLTheme.surfaceMuted, in: .rect(cornerRadius: 10))
            }
        }
        .frame(maxWidth: .infinity, alignment: message.role == .user ? .trailing : .leading)
        .id(message.id)
        .transition(.move(edge: message.role == .user ? .trailing : .leading).combined(with: .opacity))
    }

    private func submit() {
        let submitted = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !submitted.isEmpty, !isSending else { return }
        withAnimation(.spring(response: 0.35, dampingFraction: 0.82)) {
            messages.append(ChatMessage(role: .user, text: submitted))
        }
        question = ""
        isSending = true
        requestTask = Task {
            defer { isSending = false }
            do {
                let response = try await model.askBenzo(submitted)
                guard !Task.isCancelled else { return }
                withAnimation(.spring(response: 0.4, dampingFraction: 0.84)) {
                    messages.append(ChatMessage(role: .assistant, text: response.answer, suggestions: response.suggestions))
                }
            } catch is CancellationError {
                return
            } catch {
                withAnimation {
                    messages.append(ChatMessage(role: .error, text: error.localizedDescription))
                }
            }
        }
    }
}
