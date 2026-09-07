import Foundation

/// The routes the app uses, written exactly as FastAPI declares them.
///
/// **This is the one thing the app mirrors**, and it is mirrored the way
/// CLAUDE.md asks for: `tests/test_ios_client.py` reads these strings out of
/// this file and asserts every one of them is a route the service actually
/// serves. A renamed endpoint fails a Python test on a machine with no Xcode
/// on it, rather than failing on a phone.
///
/// Four routes, and the shortness is the point - this app is a window on the
/// service, not a second brain. Anything that needs a fifth is worth a second
/// look at whether it belongs here or in the service.
public enum HostRoute {
    public static let status = "/api/status"
    public static let config = "/api/config"
    public static let events = "/api/events"
    public static let trigger = "/api/trigger/{trigger}"

    /// A route template with its path parameters filled in.
    public static func path(_ template: String, _ values: [String: String]) -> String {
        values.reduce(template) { path, pair in
            path.replacingOccurrences(of: "{\(pair.key)}", with: pair.value)
        }
    }
}

public enum HostError: Error, LocalizedError, Equatable {
    /// What was typed in Settings is not an address.
    case badAddress(String)
    /// Nothing answered - wrong network, service stopped, phone on cellular.
    case unreachable(String)
    /// It answered, and said no.
    case http(Int, String)
    /// It answered with something that is not what this endpoint returns.
    case malformed(String)

    public var errorDescription: String? {
        switch self {
        case let .badAddress(text): return "\(text) is not an address."
        case let .unreachable(why): return "The service did not answer. \(why)"
        case let .http(code, detail): return "The service said \(code): \(detail)"
        case let .malformed(what): return "Unexpected answer from the service (\(what))."
        }
    }
}

/// The seam.
///
/// Two implementations, interchangeable, no downcasting - the same shape
/// `ButtonDevice` has host-side, for the same reason: every view is written
/// against this, so the whole app runs in a preview with no service, no
/// network and no button, exactly as the service runs against `MockDevice`.
public protocol HostClient: Sendable {
    func status() async throws -> Status
    func config() async throws -> ConfigSnapshot
    func events(limit: Int) async throws -> [EventRow]
    /// Fire a gesture as if the button had been pressed. The service queues it
    /// into the same path a real press takes, so what happens next is whatever
    /// the config says - the app decides nothing.
    func fire(_ gesture: String) async throws
}

/// Where the service is. Pure, so what someone typed can be checked before a
/// request is made rather than by making one.
public enum HostAddress {

    public static let defaultPort = 8080

    /// Turn what a person typed into a base URL: "192.168.1.20",
    /// "desk.local", "desk.local:8080", "http://192.168.1.20:8080" all arrive
    /// at the same place. Nil for anything without a host in it.
    public static func url(from typed: String) -> URL? {
        var text = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        if !text.contains("://") { text = "http://" + text }
        guard var parts = URLComponents(string: text),
              let host = parts.host, !host.isEmpty else { return nil }
        if parts.port == nil { parts.port = defaultPort }
        // A path, a query or a fragment is someone pasting a page rather than
        // an address; the routes below supply their own.
        parts.path = ""
        parts.query = nil
        parts.fragment = nil
        return parts.url
    }

    /// How the address should read back on screen once accepted.
    public static func display(_ url: URL) -> String {
        var text = url.host ?? url.absoluteString
        if let port = url.port, port != 80 { text += ":\(port)" }
        return text
    }
}

/// The service, over HTTP.
public struct HTTPHost: HostClient {
    public let baseURL: URL
    /// Short on purpose. A phone that has walked off the network should say so
    /// in a couple of seconds, not sit on a spinner for a minute.
    public var timeout: TimeInterval

    public init(baseURL: URL, timeout: TimeInterval = 5) {
        self.baseURL = baseURL
        self.timeout = timeout
    }

    public init?(address: String, timeout: TimeInterval = 5) {
        guard let url = HostAddress.url(from: address) else { return nil }
        self.init(baseURL: url, timeout: timeout)
    }

    public func status() async throws -> Status {
        try await get(HostRoute.status)
    }

    public func config() async throws -> ConfigSnapshot {
        try await get(HostRoute.config)
    }

    public func events(limit: Int = 50) async throws -> [EventRow] {
        try await get(HostRoute.events, query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    public func fire(_ gesture: String) async throws {
        _ = try await send(HostRoute.path(HostRoute.trigger, ["trigger": gesture]),
                           method: "POST")
    }

    // --- the plumbing -------------------------------------------------

    private func makeRequest(_ path: String, method: String,
                             query: [URLQueryItem]) throws -> URLRequest {
        guard var parts = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw HostError.badAddress(baseURL.absoluteString)
        }
        parts.path = path
        parts.queryItems = query.isEmpty ? nil : query
        guard let url = parts.url else {
            throw HostError.badAddress(baseURL.absoluteString + path)
        }
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = method
        // The service answers `no-store` on the page; ask for the same on the
        // API, because a cached status is a lie about a live button.
        request.cachePolicy = .reloadIgnoringLocalCacheData
        return request
    }

    private func send(_ path: String, method: String,
                      query: [URLQueryItem] = []) async throws -> Data {
        let request = try makeRequest(path, method: method, query: query)
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw HostError.unreachable(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else {
            throw HostError.malformed(path)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw HostError.http(http.statusCode, Self.detail(data))
        }
        return data
    }

    private func get<T: Decodable>(_ path: String,
                                   query: [URLQueryItem] = []) async throws -> T {
        let data = try await send(path, method: "GET", query: query)
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw HostError.malformed(path)
        }
    }

    /// FastAPI's refusals carry a `detail`; anything else is shown as it came.
    private static func detail(_ data: Data) -> String {
        if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = object["detail"] as? String {
            return detail
        }
        let text = String(data: data, encoding: .utf8) ?? ""
        return text.isEmpty ? "no detail" : String(text.prefix(200))
    }
}
