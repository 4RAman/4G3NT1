import SwiftUI
import ButtonKit

/// The phone, as a window on the running service.
///
/// **It decides nothing.** Every gesture it fires goes down the same path a
/// real press takes and the host resolves it, exactly as TODO 90 decided: a
/// second brain in Swift is the one shape this must not grow into. When the
/// runtime finishes moving onto the device (ARCHITECTURE Phase D/E), this app
/// becomes a preferences editor and a `Request` fulfiller - and the screens
/// below are already only ever *showing* what the host said.
@main
struct ButtonApp: App {
    @State private var store = HostStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)
        }
    }
}
