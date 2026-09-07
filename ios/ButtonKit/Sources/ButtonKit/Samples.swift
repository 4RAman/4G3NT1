import Foundation

/// Real answers, kept as the JSON they arrive as.
///
/// One set of bodies, two readers: `PreviewHost` decodes them so every view
/// renders with no service in the room, and the tests decode them so the
/// decoding is checked against something the service could actually have
/// said. Captured from `/api/status`, `/api/config` and `/api/events` with the
/// stock config running.
public enum Samples {

    public static let status = #"""
    {
      "state": "idle",
      "device_name": "AIButton",
      "uptime_s": 5231,
      "config_path": "C:/Users/me/Projects/BUTTON/config.json",
      "mode_count": 12,
      "active_modes": {
        "short_press": "Home",
        "double_tap": "Home",
        "triple_tap": null,
        "tap_4": null,
        "tap_5": "Home",
        "long_press": "Home"
      },
      "last_trigger": "short_press",
      "last_mode": "Home",
      "last_ok": true,
      "last_message": "logged",
      "version": "0.9.0",
      "mock": false,
      "device_connected": true,
      "device_info": {
        "protocol_version": 1,
        "firmware": "0.6.1",
        "capabilities": ["led", "buzzer", "palette", "effect", "gesture-params", "app-install"],
        "capabilities_absent": ["haptics", "battery", "imu", "mic", "ota"]
      },
      "store_degraded": false,
      "now": "2026-09-06T09:41:12",
      "clock_override": false,
      "led_state": "IDLE",
      "led_effect": null,
      "last_sound": null,
      "sound_seq": 14,
      "led_palette": {
        "IDLE": {"style": "breathe", "color": "#1e40ff", "color2": null, "period_s": 4.0},
        "LISTENING": {"style": "solid", "color": "#ffcc00", "color2": null, "period_s": null},
        "SUCCESS": {"style": "solid", "color": "#00cc44", "color2": null, "period_s": null},
        "ALERT": {"style": "alternate", "color": "#ff0000", "color2": "#ffffff", "period_s": 0.4}
      }
    }
    """#

    public static let config = #"""
    {
      "path": "C:/Users/me/Projects/BUTTON/config.json",
      "write_path": "C:/Users/me/Projects/BUTTON/scenes/desk.json",
      "scene": "desk",
      "warnings": [],
      "warning_details": [],
      "effective": {
        "modes": [
          {"name": "Home", "template": "actions", "activation": {"type": "always"},
           "short_press": {"action": "log", "name": "note"},
           "double_tap": {"action": "enter_mode", "name": "Apps"}},
          {"name": "Apps", "template": "launcher", "activation": {"type": "manual"}},
          {"name": "Morning meds", "template": "notice",
           "activation": {"type": "schedule", "at": "07:30", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"]},
           "message": "Take your tablets", "urgent": true},
          {"name": "Focus", "template": "pomodoro",
           "activation": {"type": "window", "between": ["09:00", "17:00"]}}
        ]
      }
    }
    """#

    public static let events = #"""
    [
      {"ts": "2026-09-06T09:40:02", "kind": "log", "name": "note", "duration_s": null,
       "mode": "Home", "value": null},
      {"ts": "2026-09-06T09:12:44", "kind": "mode_exit", "name": "Focus", "duration_s": 1500.0,
       "mode": "Focus", "value": null},
      {"ts": "2026-09-06T08:47:44", "kind": "mode_enter", "name": "Focus", "duration_s": null,
       "mode": "Focus", "value": null},
      {"ts": "2026-09-06T07:30:00", "kind": "notice", "name": "Morning meds", "duration_s": null,
       "mode": "Morning meds", "value": null}
    ]
    """#
}

/// The service, faked.
///
/// `MockDevice`'s counterpart one tier up: the views are written against
/// `HostClient` and this is what they get in a preview, so the whole app is
/// walkable with no service running, no network, and no button.
public struct PreviewHost: HostClient {
    /// Set to something to see how the app reads when the service is down -
    /// which is the state a phone spends most of its day in.
    public var failure: HostError?
    /// A moment, so the loading state is visible rather than theoretical.
    public var latency: Duration

    public init(failure: HostError? = nil, latency: Duration = .milliseconds(120)) {
        self.failure = failure
        self.latency = latency
    }

    public func status() async throws -> Status { try await decode(Samples.status) }
    public func config() async throws -> ConfigSnapshot { try await decode(Samples.config) }

    public func events(limit: Int) async throws -> [EventRow] {
        let rows: [EventRow] = try await decode(Samples.events)
        return Array(rows.prefix(limit))
    }

    public func fire(_ gesture: String) async throws {
        try await Task.sleep(for: latency)
        if let failure { throw failure }
    }

    private func decode<T: Decodable>(_ json: String) async throws -> T {
        try await Task.sleep(for: latency)
        if let failure { throw failure }
        return try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }
}
