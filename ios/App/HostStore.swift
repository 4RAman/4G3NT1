import Foundation
import Observation
import ButtonKit

/// Everything the app knows, which is only ever what the service last said.
///
/// The one piece of state it owns is the address; the rest is a cache of
/// answers with a timestamp on it. That asymmetry is deliberate - config never
/// flows upward from here and app state never flows downward into here, which
/// is ARCHITECTURE.md's ownership rule arriving one tier early.
@Observable
@MainActor
final class HostStore {

    private static let addressKey = "button.host.address"

    /// What was typed in Settings. Persisted, because typing an IP address on
    /// a phone once is enough.
    var address: String

    private(set) var client: (any HostClient)?
    private(set) var status: Status?
    private(set) var config: ConfigSnapshot?
    private(set) var events: [EventRow] = []

    /// Why the last attempt failed, or nil. Shown rather than logged: a phone
    /// that has walked off the network has to say so.
    private(set) var lastError: String?
    private(set) var lastAnswer: Date?
    /// Which gesture is in flight, so its button can say so.
    private(set) var firing: String?
    /// Bumped on every accepted press, purely so the view has something to
    /// hang haptic feedback off.
    private(set) var fireCount = 0

    var isReachable: Bool { status != nil && lastError == nil }
    var hasAddress: Bool { client != nil }

    /// The preview host is injected the same way `MockDevice` is: the app has
    /// no idea which one it got.
    ///
    /// `nonisolated` because `@State private var store = HostStore()` in the
    /// App struct runs outside any actor - it only fills in stored properties,
    /// which is exactly what a nonisolated init is allowed to do.
    nonisolated init(client: (any HostClient)? = nil) {
        let saved = UserDefaults.standard.string(forKey: Self.addressKey) ?? ""
        address = saved
        self.client = client ?? HTTPHost(address: saved)
    }

    /// Accept what was typed, or say why it is not an address. Checked before
    /// a request is made, so "that is not an address" and "nothing answered"
    /// stay two different sentences.
    @discardableResult
    func connect() -> Bool {
        guard let url = HostAddress.url(from: address) else {
            lastError = HostError.badAddress(address).errorDescription
            return false
        }
        address = HostAddress.display(url)
        UserDefaults.standard.set(address, forKey: Self.addressKey)
        client = HTTPHost(baseURL: url)
        status = nil
        config = nil
        events = []
        lastError = nil
        return true
    }

    /// Status only, on a loop. Config and events are fetched by the screens
    /// that show them: the config is large and changes when someone edits it,
    /// not twice a second.
    func poll(every seconds: Double = 2) async {
        while !Task.isCancelled {
            await refreshStatus()
            try? await Task.sleep(for: .seconds(seconds))
        }
    }

    func refreshStatus() async {
        guard let client else { return }
        do {
            status = try await client.status()
            lastAnswer = Date()
            lastError = nil
        } catch {
            note(error)
        }
    }

    func loadConfig() async {
        guard let client else { return }
        do {
            config = try await client.config()
            lastError = nil
        } catch {
            note(error)
        }
    }

    func loadEvents(limit: Int = 100) async {
        guard let client else { return }
        do {
            events = try await client.events(limit: limit)
            lastError = nil
        } catch {
            note(error)
        }
    }

    /// Fire a gesture. The host decides what it means; this only reports what
    /// happened next by refreshing.
    func fire(_ gesture: String) async {
        guard let client else { return }
        firing = gesture
        defer { firing = nil }
        do {
            try await client.fire(gesture)
            fireCount += 1
            lastError = nil
            await refreshStatus()
        } catch {
            note(error)
        }
    }

    private func note(_ error: Error) {
        lastError = (error as? LocalizedError)?.errorDescription
            ?? error.localizedDescription
    }
}
