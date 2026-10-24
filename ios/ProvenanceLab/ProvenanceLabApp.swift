import SwiftUI

@main
struct ProvenanceLabApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .tint(PLTheme.blue)
        }
    }
}
