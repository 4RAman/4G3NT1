import Foundation

/// Per-key fallback, in Swift.
///
/// `config.py` never lets one bad key take a whole config down - every field
/// falls back individually and the failure is reported rather than thrown. The
/// phone is one more consumer of the same JSON and wants the same promise from
/// the other end: a service that grows a field, renames one, or answers with a
/// null where the app expected a number must not blank the screen.
///
/// So nothing in `Models.swift` uses synthesised `Decodable`. Every field goes
/// through one of these two, which is the same shape as `config._take`.
extension KeyedDecodingContainer {

    /// The value at `key`, or `fallback` if it is missing, null, or the wrong
    /// type. Never throws.
    func value<T: Decodable>(_ key: Key, or fallback: T) -> T {
        guard let found = try? decodeIfPresent(T.self, forKey: key) else {
            return fallback
        }
        return found ?? fallback
    }

    /// The value at `key`, or nil for missing / null / wrong type. Never throws.
    func optional<T: Decodable>(_ key: Key) -> T? {
        (try? decodeIfPresent(T.self, forKey: key)) ?? nil
    }
}

/// Any JSON, kept as it arrived.
///
/// The effective config is a large, growing object and the app reads a
/// handful of its keys. Decoding the rest into Swift types would make every
/// new config field a Swift change and every unknown one an error - so the
/// parts the app does not model are carried as this and either shown as text
/// or ignored.
public enum JSONValue: Decodable, Sendable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([String: JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            self = .null
        }
    }

    public var stringValue: String? {
        if case let .string(value) = self { return value }
        return nil
    }

    public var arrayValue: [JSONValue]? {
        if case let .array(value) = self { return value }
        return nil
    }

    public subscript(key: String) -> JSONValue? {
        if case let .object(fields) = self { return fields[key] }
        return nil
    }

    /// One line of plain text, for anything the app has no view for.
    public var summary: String {
        switch self {
        case let .string(value): return value
        case let .number(value):
            return value == value.rounded()
                ? String(Int(value))
                : String(format: "%g", value)
        case let .bool(value): return value ? "yes" : "no"
        case let .array(items): return items.map(\.summary).joined(separator: ", ")
        case let .object(fields):
            return fields.keys.sorted()
                .map { "\($0): \(fields[$0]!.summary)" }
                .joined(separator: ", ")
        case .null: return ""
        }
    }
}
