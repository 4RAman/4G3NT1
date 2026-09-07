import SwiftUI
import ButtonKit

struct RootView: View {
    @Environment(HostStore.self) private var store

    var body: some View {
        Group {
            if store.hasAddress {
                TabView {
                    NowView()
                        .tabItem { Label("Now", systemImage: "circle.circle.fill") }
                    ModesView()
                        .tabItem { Label("Modes", systemImage: "square.stack") }
                    EventsView()
                        .tabItem { Label("Log", systemImage: "list.bullet.rectangle") }
                    SettingsView()
                        .tabItem { Label("Settings", systemImage: "gearshape") }
                }
            } else {
                SetupView()
            }
        }
        // One poll for the whole app, cancelled when it goes away. Status only
        // - see HostStore.poll.
        .task { await store.poll() }
    }
}

/// First run: no address yet, and nothing to show until there is one.
struct SetupView: View {
    @Environment(HostStore.self) private var store

    var body: some View {
        @Bindable var store = store
        NavigationStack {
            Form {
                Section {
                    TextField("192.168.1.20", text: $store.address)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    Button("Connect") { store.connect() }
                        .disabled(store.address.isEmpty)
                } header: {
                    Text("Where the service is running")
                } footer: {
                    Text("The machine running the button service, on the same "
                         + "network as this phone. The port is 8080 unless you say "
                         + "otherwise. A name like desk.local works too.")
                }
                if let error = store.lastError {
                    Section { Text(error).foregroundStyle(.red) }
                }
            }
            .navigationTitle("The button")
        }
    }
}

#Preview("Setup") {
    RootView().environment(HostStore())
}

#Preview("Connected") {
    RootView().environment(HostStore(client: PreviewHost()))
}
