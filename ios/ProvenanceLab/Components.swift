import SwiftUI
import UIKit
import WebKit

enum PLTheme {
    static let background = adaptive(light: 0xF2F6FA, dark: 0x09141E)
    static let surfaceMuted = adaptive(light: 0xF5FAFF, dark: 0x122231)
    static let ink = adaptive(light: 0x102539, dark: 0xEAF5FF)
    static let inkSoft = adaptive(light: 0x29435B, dark: 0xC2D5E5)
    static let muted = adaptive(light: 0x71869A, dark: 0x8DA4B8)
    static let border = adaptive(light: 0xD7E2EC, dark: 0x2B4052)
    static let cyan = Color(hex: 0x25CEC4)
    static let blue = Color(hex: 0x2E9AF5)
    static let violet = Color(hex: 0x966CF1)
    static let magenta = Color(hex: 0xED48CC)
    static let verified = Color(hex: 0x087B73)
    static let ambiguous = Color(hex: 0xC66A00)
    static let invalid = Color(hex: 0xC31F58)

    static var spectrum: LinearGradient {
        LinearGradient(colors: [cyan, blue, violet, magenta], startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    private static func adaptive(light: UInt, dark: UInt) -> Color {
        Color(uiColor: UIColor { traits in UIColor(hex: traits.userInterfaceStyle == .dark ? dark : light) })
    }
}

extension Color {
    init(hex: UInt, alpha: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: alpha
        )
    }
}

private extension UIColor {
    convenience init(hex: UInt) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}

struct BrandMark: View {
    var size: CGFloat = 38

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.28, style: .continuous)
                .fill(PLTheme.ink)
            Text("P")
                .font(.system(size: size * 0.52, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
            Circle()
                .fill(PLTheme.cyan)
                .frame(width: size * 0.22)
                .offset(x: size * 0.28, y: size * 0.28)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

struct MoleculeOrb: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var rotating = false

    var body: some View {
        ZStack {
            Circle()
                .fill(PLTheme.spectrum.opacity(0.16))
                .blur(radius: 18)
                .scaleEffect(rotating && !reduceMotion ? 1.12 : 0.92)
            Circle()
                .stroke(PLTheme.spectrum, lineWidth: 2)
                .frame(width: 126, height: 126)
            ForEach(0..<6, id: \.self) { index in
                Capsule()
                    .fill(PLTheme.inkSoft.opacity(0.7))
                    .frame(width: 52, height: 2)
                    .offset(x: 46)
                    .rotationEffect(.degrees(Double(index) * 60))
            }
            ForEach(0..<6, id: \.self) { index in
                Circle()
                    .fill(index.isMultiple(of: 2) ? PLTheme.cyan : PLTheme.magenta)
                    .frame(width: 13, height: 13)
                    .offset(x: 72)
                    .rotationEffect(.degrees(Double(index) * 60))
            }
            Image(systemName: "atom")
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(PLTheme.ink)
        }
        .frame(width: 190, height: 190)
        .rotationEffect(.degrees(rotating && !reduceMotion ? 360 : 0))
        .animation(.linear(duration: 24).repeatForever(autoreverses: false), value: rotating)
        .onAppear { rotating = true }
    }
}

struct StatusPill: View {
    var status: MoleculeStatus

    private var color: Color {
        switch status {
        case .valid: PLTheme.verified
        case .ambiguous: PLTheme.ambiguous
        case .invalid: PLTheme.invalid
        }
    }

    var body: some View {
        Label(status.rawValue.capitalized, systemImage: status == .valid ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
            .font(.caption.weight(.bold))
            .foregroundStyle(color)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(color.opacity(0.11), in: .capsule)
    }
}

struct HashRow: View {
    var label: String
    var value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label.uppercased())
                .font(.caption2.weight(.bold))
                .foregroundStyle(PLTheme.muted)
            Text(value)
                .font(.caption.monospaced())
                .foregroundStyle(PLTheme.inkSoft)
                .textSelection(.enabled)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct LoadingOverlay: View {
    var message: String

    var body: some View {
        ZStack {
            Color.black.opacity(0.16).ignoresSafeArea()
            VStack(spacing: 14) {
                ProgressView().controlSize(.large).tint(PLTheme.cyan)
                Text(message)
                    .font(.subheadline.weight(.semibold))
                    .multilineTextAlignment(.center)
            }
            .padding(24)
            .background(.regularMaterial, in: .rect(cornerRadius: 18))
            .padding()
        }
        .transition(.opacity)
    }
}

struct SVGView: UIViewRepresentable {
    var svg: String

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.isOpaque = false
        view.backgroundColor = .clear
        view.scrollView.isScrollEnabled = false
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        let html = """
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>html,body{margin:0;width:100%;height:100%;display:grid;place-items:center;background:transparent}svg{width:100%;height:100%;max-width:100%;max-height:100%}</style>
        \(svg)
        """
        view.loadHTMLString(html, baseURL: nil)
    }
}

struct ActivityShareSheet: UIViewControllerRepresentable {
    var items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
