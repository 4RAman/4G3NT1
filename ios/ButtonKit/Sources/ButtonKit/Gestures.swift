import Foundation

/// Gesture names, and nothing that has to be kept in step with the host.
///
/// There is deliberately **no table of gestures here.** `TriggerType` is the
/// host's, and the app learns the list at runtime from `/api/status`'s
/// `active_modes`, which is keyed by exactly `TRIGGER_TYPES`. So a tap count
/// added host-side - which ROADMAP D5 made a data change with no reflash under
/// it - reaches the phone with no Swift edit and nothing to drift.
///
/// What is here is presentation: an order to show them in and a label to show
/// them as, both of which degrade to something readable for a name this file
/// has never seen.
public enum Gesture {

    /// The order gestures read in - shortest to longest, with "up one level"
    /// last because that is where it sits in every other surface. A name not
    /// in this list is not dropped: it sorts after these, alphabetically. So
    /// the worst a stale order can do is put a new gesture in the wrong place.
    public static let preferredOrder = [
        "short_press", "double_tap", "triple_tap", "tap_4", "tap_5", "long_press",
    ]

    public static func ordered(_ names: some Collection<String>) -> [String] {
        let known = names.filter { preferredOrder.contains($0) }
        let rest = names.filter { !preferredOrder.contains($0) }.sorted()
        return preferredOrder.filter { known.contains($0) } + rest
    }

    /// "double_tap" -> "Double tap", "tap_4" -> "4 taps". Derived, so a
    /// gesture name arriving from a newer host still reads as English.
    public static func label(_ name: String) -> String {
        if let count = tapCount(name) {
            return "\(count) taps"
        }
        let spaced = name.replacingOccurrences(of: "_", with: " ")
        return spaced.prefix(1).uppercased() + spaced.dropFirst()
    }

    /// The N in `tap_N`, for the counted gestures that name themselves that
    /// way. Nil for `short_press`, `double_tap` and anything else.
    public static func tapCount(_ name: String) -> Int? {
        guard name.hasPrefix("tap_") else { return nil }
        return Int(name.dropFirst("tap_".count))
    }
}
