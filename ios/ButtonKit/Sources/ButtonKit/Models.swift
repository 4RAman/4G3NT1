import Foundation

// What the service answers with. One struct per endpoint, decoded key by key
// (see Decoding.swift) so a field the host adds or drops is not an outage on
// the phone.

/// A look: what the light is doing. The same nine bytes the wire carries,
/// which is why the palette and the ephemeral effect are one type here exactly
/// as they are one function (`webui._effect_dict`) there.
public struct LedEffect: Decodable, Sendable, Equatable {
    public var style: String
    public var color: String?
    public var color2: String?
    public var periodS: Double?

    enum CodingKeys: String, CodingKey {
        case style, color, color2
        case periodS = "period_s"
    }

    public init(style: String, color: String? = nil,
                color2: String? = nil, periodS: Double? = nil) {
        self.style = style
        self.color = color
        self.color2 = color2
        self.periodS = periodS
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        // An unknown style renders steady rather than not at all - see Look.swift.
        style = c.value(.style, or: "solid")
        color = c.optional(.color)
        color2 = c.optional(.color2)
        periodS = c.optional(.periodS)
    }
}

/// What the button said it is, when the host last asked it.
public struct DeviceInfo: Decodable, Sendable, Equatable {
    /// 0 means the firmware predates `DEVICE_INFO`, so the rest is an
    /// assumption the host made rather than an answer the device gave.
    public var protocolVersion: Int
    public var firmware: String
    public var capabilities: [String]
    public var capabilitiesAbsent: [String]

    enum CodingKeys: String, CodingKey {
        case protocolVersion = "protocol_version"
        case firmware
        case capabilities
        case capabilitiesAbsent = "capabilities_absent"
    }

    public init(protocolVersion: Int = 0, firmware: String = "0.0.0",
                capabilities: [String] = [], capabilitiesAbsent: [String] = []) {
        self.protocolVersion = protocolVersion
        self.firmware = firmware
        self.capabilities = capabilities
        self.capabilitiesAbsent = capabilitiesAbsent
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        protocolVersion = c.value(.protocolVersion, or: 0)
        firmware = c.value(.firmware, or: "0.0.0")
        capabilities = c.value(.capabilities, or: [])
        capabilitiesAbsent = c.value(.capabilitiesAbsent, or: [])
    }

    public func has(_ capability: String) -> Bool {
        capabilities.contains(capability)
    }
}

/// `GET /api/status` - everything the phone needs to draw one screen.
public struct Status: Decodable, Sendable, Equatable {
    public var state: String
    public var deviceName: String
    public var version: String
    public var uptimeS: Int
    public var configPath: String
    public var modeCount: Int

    /// Every gesture the host knows about, in the order it means to offer
    /// them. Read off `active_modes`, which is keyed by exactly the host's
    /// `TRIGGER_TYPES` - so the app has no gesture table to keep in step.
    public var gestures: [String]
    /// Which mode would answer each gesture right now. A gesture nothing
    /// answers is absent here and present in `gestures`.
    public var activeModes: [String: String]

    /// False while a real button is out of range or unplugged. The service
    /// keeps running, so the app has to say why nothing lights up.
    public var deviceConnected: Bool
    /// True when there is no hardware behind the seam at all.
    public var mock: Bool
    public var deviceInfo: DeviceInfo
    /// True when history is in memory only, so the Events list will empty
    /// itself on the next restart.
    public var storeDegraded: Bool

    public var ledState: String
    /// The one-off look a takeover is pushing, if any. Null falls back to the
    /// palette entry for `ledState`, which is what the device is rendering.
    public var ledEffect: LedEffect?
    public var ledPalette: [String: LedEffect]

    public var lastTrigger: String?
    public var lastMode: String?
    public var lastOk: Bool?
    public var lastMessage: String?
    public var lastSound: String?
    public var now: String?
    public var clockOverride: Bool

    enum CodingKeys: String, CodingKey {
        case state, version, mock, now
        case deviceName = "device_name"
        case uptimeS = "uptime_s"
        case configPath = "config_path"
        case modeCount = "mode_count"
        case activeModes = "active_modes"
        case deviceConnected = "device_connected"
        case deviceInfo = "device_info"
        case storeDegraded = "store_degraded"
        case ledState = "led_state"
        case ledEffect = "led_effect"
        case ledPalette = "led_palette"
        case lastTrigger = "last_trigger"
        case lastMode = "last_mode"
        case lastOk = "last_ok"
        case lastMessage = "last_message"
        case lastSound = "last_sound"
        case clockOverride = "clock_override"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        state = c.value(.state, or: "unknown")
        deviceName = c.value(.deviceName, or: "the button")
        version = c.value(.version, or: "")
        uptimeS = c.value(.uptimeS, or: 0)
        configPath = c.value(.configPath, or: "")
        modeCount = c.value(.modeCount, or: 0)

        // `active_modes` carries a null for every gesture no mode answers, and
        // both halves matter: the keys are the gesture list, the non-null
        // values are what a press would reach.
        let resolved: [String: String?] = c.value(.activeModes, or: [:])
        gestures = Gesture.ordered(resolved.keys)
        activeModes = resolved.compactMapValues { $0 }

        deviceConnected = c.value(.deviceConnected, or: false)
        mock = c.value(.mock, or: false)
        deviceInfo = c.value(.deviceInfo, or: DeviceInfo())
        storeDegraded = c.value(.storeDegraded, or: false)

        ledState = c.value(.ledState, or: "IDLE")
        ledEffect = c.optional(.ledEffect)
        let palette: [String: LedEffect?] = c.value(.ledPalette, or: [:])
        ledPalette = palette.compactMapValues { $0 }

        lastTrigger = c.optional(.lastTrigger)
        lastMode = c.optional(.lastMode)
        lastOk = c.optional(.lastOk)
        lastMessage = c.optional(.lastMessage)
        lastSound = c.optional(.lastSound)
        now = c.optional(.now)
        clockOverride = c.value(.clockOverride, or: false)
    }

    /// What the light is actually doing: the pushed look if a takeover is
    /// pushing one, else the palette entry the state names. Same precedence as
    /// the web UI's virtual device, and for the same reason - an effect is
    /// shown, not stored, so it wins until the next state change.
    public var currentLook: LedEffect? {
        ledEffect ?? ledPalette[ledState]
    }
}

/// One mode, as the effective config describes it.
///
/// Three keys are modelled because `_mode_to_dict` always writes them; the
/// rest of a mode is per-template and stays as `extras`, so a template the app
/// has never heard of still lists and still says what it is.
public struct ModeSummary: Decodable, Sendable, Equatable, Identifiable {
    public var name: String
    public var template: String
    public var activation: JSONValue
    public var extras: [String: JSONValue]

    public var id: String { name }

    private struct AnyKey: CodingKey {
        var stringValue: String
        var intValue: Int? { nil }
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { return nil }
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: AnyKey.self)
        var fields: [String: JSONValue] = [:]
        for key in c.allKeys {
            fields[key.stringValue] = c.value(key, or: JSONValue.null)
        }
        name = fields["name"]?.stringValue ?? "(unnamed)"
        template = fields["template"]?.stringValue ?? "actions"
        activation = fields["activation"] ?? .null
        fields.removeValue(forKey: "name")
        fields.removeValue(forKey: "template")
        fields.removeValue(forKey: "activation")
        extras = fields
    }

    /// "Always on", "Daily at 07:00", "Mon-Fri 09:00-17:00" - one line,
    /// derived rather than tabled, so an activation type the app does not know
    /// still reads as something.
    public var activationSummary: String {
        let type = activation["type"]?.stringValue ?? "always"
        let days = activation["days"]?.arrayValue?.compactMap(\.stringValue) ?? []
        let dayText = days.isEmpty ? "" : " " + days.joined(separator: " ")
        switch type {
        case "always": return "Always on"
        case "manual": return "Only when opened"
        case "schedule":
            let at = activation["at"]?.stringValue ?? "?"
            return "At \(at)\(dayText)"
        case "window":
            let span = activation["between"]?.arrayValue?
                .compactMap(\.stringValue).joined(separator: "-")
            return (span.map { "Between \($0)" } ?? "In a window") + dayText
        default:
            return type.capitalized + dayText
        }
    }
}

/// `GET /api/config`. `raw` and `effective` are both served; the app reads
/// `effective`, because that is what the button is actually running.
public struct ConfigSnapshot: Decodable, Sendable, Equatable {
    public var path: String
    /// Where a Save would land - the active scene's file, when there is one.
    public var writePath: String?
    public var scene: String?
    public var warnings: [String]
    public var modes: [ModeSummary]

    private struct Effective: Decodable {
        var modes: [ModeSummary]
        enum CodingKeys: String, CodingKey { case modes }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            modes = c.value(.modes, or: [])
        }
    }

    enum CodingKeys: String, CodingKey {
        case path, scene, warnings, effective
        case writePath = "write_path"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        path = c.value(.path, or: "")
        writePath = c.optional(.writePath)
        scene = c.optional(.scene)
        warnings = c.value(.warnings, or: [])
        let effective: Effective? = c.optional(.effective)
        modes = effective?.modes ?? []
    }
}

/// One row of the log. `duration_s` and `value` are per-kind and usually null.
public struct EventRow: Decodable, Sendable, Equatable, Identifiable {
    public var ts: String
    public var kind: String
    public var name: String
    public var durationS: Double?
    public var mode: String?
    public var value: Double?

    /// The log has no row ids, and two rows can share a timestamp - so the
    /// identity is the row's content plus where it sat in the page.
    public var id: String { "\(ts)|\(kind)|\(name)|\(mode ?? "")|\(value ?? 0)" }

    enum CodingKeys: String, CodingKey {
        case ts, kind, name, mode, value
        case durationS = "duration_s"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ts = c.value(.ts, or: "")
        kind = c.value(.kind, or: "")
        name = c.value(.name, or: "")
        durationS = c.optional(.durationS)
        mode = c.optional(.mode)
        value = c.optional(.value)
    }
}

/// Timestamps, read leniently.
///
/// The log writes what the host's clock said, and the exact spelling has never
/// been a promise. The answer to "cannot parse" is showing the raw string, not
/// dropping the row - a log you cannot read the time of is still a log.
public enum Timestamps {

    public static func parse(_ text: String) -> Date? {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return nil }

        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = iso.date(from: trimmed) { return date }
        iso.formatOptions = [.withInternetDateTime]
        if let date = iso.date(from: trimmed) { return date }

        // No timezone at all is the ordinary case: the store writes the host's
        // own wall clock, so read it as this device's local time.
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSS", "yyyy-MM-dd'T'HH:mm:ss",
                       "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd'T'HH:mm"] {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = .current
            formatter.dateFormat = format
            if let date = formatter.date(from: trimmed) { return date }
        }
        return nil
    }
}

extension EventRow {
    /// When the row says it happened, or nil - in which case show `ts` as it
    /// arrived.
    public var date: Date? { Timestamps.parse(ts) }
}
