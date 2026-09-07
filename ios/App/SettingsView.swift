import SwiftUI
import ButtonKit

struct SettingsView: View {
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
                } header: {
                    Text("Service")
                } footer: {
                    if let error = store.lastError {
                        Text(error).foregroundStyle(.red)
                    } else if let at = store.lastAnswer {
                        Text("Answered at \(at.formatted(date: .omitted, time: .standard)).")
                    }
                }

                if let status = store.status {
                    Section("The service") {
                        row("Version", status.version)
                        row("Uptime", uptime(status.uptimeS))
                        row("Modes", String(status.modeCount))
                        if let config = store.config {
                            row("Config", (config.path as NSString).lastPathComponent)
                            if let scene = config.scene { row("Scene", scene) }
                        }
                    }

                    Section {
                        row("Name", status.deviceName)
                        row("Connected", status.deviceConnected ? "yes" : "no")
                        row("Firmware", status.deviceInfo.firmware)
                        row("Protocol", status.deviceInfo.protocolVersion == 0
                            ? "before DEVICE_INFO"
                            : "v\(status.deviceInfo.protocolVersion)")
                        if !status.deviceInfo.capabilities.isEmpty {
                            row("Has", status.deviceInfo.capabilities.joined(separator: ", "))
                        }
                    } header: {
                        Text("The button")
                    } footer: {
                        if status.deviceInfo.protocolVersion == 0 {
                            Text("This firmware predates DEVICE_INFO, so what it "
                                 + "can do is assumed rather than answered.")
                        }
                    }
                }

                Section {
                    Text("This app is a window on the service. Every decision - "
                         + "what a press means, what the light does, what gets "
                         + "logged - is made by the host, so the app and the web "
                         + "UI can never disagree. It does nothing while that "
                         + "machine is off.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                } header: {
                    Text("What this is")
                }
            }
            .navigationTitle("Settings")
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(value)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.trailing)
        }
        .font(.callout)
    }

    private func uptime(_ seconds: Int) -> String {
        if seconds < 3600 { return "\(seconds / 60) min" }
        if seconds < 86400 { return "\(seconds / 3600) h \((seconds % 3600) / 60) min" }
        return "\(seconds / 86400) d"
    }
}

#Preview {
    SettingsView().environment(HostStore(client: PreviewHost()))
}
