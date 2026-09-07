import XCTest
@testable import ButtonKit

final class LookTests: XCTestCase {

    private func decode<T: Decodable>(_ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    func testAPushedEffectWinsAndNoEffectFallsBackToThePalette() throws {
        let fromPalette: Status = try decode(Samples.status)
        XCTAssertEqual(fromPalette.currentLook?.style, "breathe")

        let pushed: Status = try decode(#"""
        {"led_state": "IDLE",
         "led_effect": {"style": "flash", "color": "#ff0000", "period_s": 0.5},
         "led_palette": {"IDLE": {"style": "breathe", "color": "#1e40ff"}}}
        """#)
        XCTAssertEqual(pushed.currentLook?.style, "flash")
    }

    func testColoursParseInTheFormsConfigWritesThem() {
        XCTAssertEqual(RGB(hex: "#ff0000"), RGB(red: 1, green: 0, blue: 0))
        XCTAssertEqual(RGB(hex: "00ff00"), RGB(red: 0, green: 1, blue: 0))
        XCTAssertEqual(RGB(hex: "#f00"), RGB(red: 1, green: 0, blue: 0))
        XCTAssertNil(RGB(hex: "rebeccapurple"))
        XCTAssertNil(RGB(hex: nil))
    }

    func testAnUnknownStyleSitsStillRatherThanDrawingNothing() {
        let swatch = Look.swatch(LedEffect(style: "shimmer", color: "#ff8800"))
        XCTAssertEqual(swatch.motion, .steady)
        XCTAssertEqual(swatch.base, RGB(hex: "#ff8800"))
    }

    func testAStyleWithNoPeriodGetsOneRatherThanDividingByZero() {
        let swatch = Look.swatch(LedEffect(style: "breathe", color: "#1e40ff"))
        XCTAssertEqual(swatch.motion, .pulse)
        XCTAssertEqual(swatch.periodS, 1)
    }

    func testNoLookAtAllIsTheUnlitColour() {
        XCTAssertEqual(Look.swatch(nil).base, RGB.unlit)
    }
}

final class GestureTests: XCTestCase {

    func testLabelsAreDerivedSoANewerHostStillReadsAsEnglish() {
        XCTAssertEqual(Gesture.label("short_press"), "Short press")
        XCTAssertEqual(Gesture.label("double_tap"), "Double tap")
        XCTAssertEqual(Gesture.label("tap_4"), "4 taps")
        XCTAssertEqual(Gesture.label("tap_9"), "9 taps")
        XCTAssertEqual(Gesture.label("wiggle"), "Wiggle")
    }

    func testAnUnknownGestureSortsAfterTheKnownOnesRatherThanVanishing() {
        let ordered = Gesture.ordered(["zebra", "long_press", "aardvark", "short_press"])
        XCTAssertEqual(ordered, ["short_press", "long_press", "aardvark", "zebra"])
    }
}

final class PreviewHostTests: XCTestCase {

    func testTheAppRunsWithNothingPluggedIn() async throws {
        let host = PreviewHost(latency: .zero)
        let status = try await host.status()
        XCTAssertEqual(status.deviceName, "AIButton")
        let config = try await host.config()
        XCTAssertEqual(config.modes.count, 4)
        let events = try await host.events(limit: 2)
        XCTAssertEqual(events.count, 2)
    }

    func testAFailingHostFailsEveryCallSoTheErrorPathIsWalkable() async {
        let host = PreviewHost(failure: .unreachable("preview"), latency: .zero)
        do {
            _ = try await host.status()
            XCTFail("expected the preview host to refuse")
        } catch {
            XCTAssertEqual(error as? HostError, .unreachable("preview"))
        }
    }
}

/// The light is the product, so what it does over time is tested rather than
/// watched: `Look.render` is the whole of the phone's animation.
final class RenderTests: XCTestCase {

    private func assertColour(_ got: RGB, _ want: RGB,
                              _ message: String = "",
                              file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(got.red, want.red, accuracy: 0.001, message, file: file, line: line)
        XCTAssertEqual(got.green, want.green, accuracy: 0.001, message, file: file, line: line)
        XCTAssertEqual(got.blue, want.blue, accuracy: 0.001, message, file: file, line: line)
    }

    func testASolidLookIsTheSameColourAtEveryMoment() {
        let look = LedEffect(style: "solid", color: "#ff8800")
        for t in [0.0, 0.37, 12.5, 900.0] {
            assertColour(Look.render(look, at: t), RGB(hex: "#ff8800")!, "t=\(t)")
        }
    }

    func testAFlashIsOnForTheFirstHalfOfItsPeriodAndOffForTheSecond() {
        let look = LedEffect(style: "flash", color: "#ff0000", periodS: 2)
        assertColour(Look.render(look, at: 0), RGB(red: 1, green: 0, blue: 0))
        assertColour(Look.render(look, at: 0.9), RGB(red: 1, green: 0, blue: 0))
        assertColour(Look.render(look, at: 1.1), RGB.off)
        assertColour(Look.render(look, at: 2.0), RGB(red: 1, green: 0, blue: 0), "wraps")
    }

    func testAnAlternateSwapsColoursAndAFadeCrossesBetweenThem() {
        let swapping = LedEffect(style: "alternate", color: "#ff0000",
                                 color2: "#0000ff", periodS: 1)
        assertColour(Look.render(swapping, at: 0), RGB(red: 1, green: 0, blue: 0))
        assertColour(Look.render(swapping, at: 0.75), RGB(red: 0, green: 0, blue: 1))

        let fading = LedEffect(style: "fade", color: "#ff0000",
                               color2: "#0000ff", periodS: 1)
        assertColour(Look.render(fading, at: 0), RGB(red: 1, green: 0, blue: 0))
        assertColour(Look.render(fading, at: 0.5), RGB(red: 0, green: 0, blue: 1))
        assertColour(Look.render(fading, at: 0.25), RGB(red: 0.5, green: 0, blue: 0.5), "halfway")
    }

    func testABreatheNeverReachesBlackBecauseThatWouldReadAsAFlash() {
        let look = LedEffect(style: "breathe", color: "#ffffff", periodS: 4)
        assertColour(Look.render(look, at: 0), RGB(red: 0.15, green: 0.15, blue: 0.15))
        assertColour(Look.render(look, at: 2), RGB(red: 1, green: 1, blue: 1))
    }

    func testARainbowTakesItsBrightnessFromTheColourTheDeviceWouldRead() {
        let full = LedEffect(style: "rainbow", color: "#ffffff", periodS: 6)
        assertColour(Look.render(full, at: 0), RGB(red: 1, green: 0, blue: 0), "hue 0 is red")

        let dimmed = LedEffect(style: "rainbow", color: "#404040", periodS: 6)
        XCTAssertEqual(Look.render(dimmed, at: 0).level, 0.251, accuracy: 0.002)
    }

    func testNoLookIsTheUnlitColourAtEveryMoment() {
        assertColour(Look.render(nil, at: 0), RGB.unlit)
        assertColour(Look.render(nil, at: 3.3), RGB.unlit)
    }
}
