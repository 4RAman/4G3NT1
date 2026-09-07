import XCTest
@testable import ButtonKit

/// Named for the scenario, not the method - and the scenarios worth naming
/// here are the ones that decide whether the app survives a service that has
/// grown a field, dropped one, or answered with less than the app expected.
final class DecodingTests: XCTestCase {

    private func decode<T: Decodable>(_ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    func testAStatusDecodesEverythingTheScreenNeeds() throws {
        let status: Status = try decode(Samples.status)
        XCTAssertEqual(status.deviceName, "AIButton")
        XCTAssertTrue(status.deviceConnected)
        XCTAssertFalse(status.mock)
        XCTAssertEqual(status.deviceInfo.protocolVersion, 1)
        XCTAssertTrue(status.deviceInfo.has("effect"))
        XCTAssertFalse(status.deviceInfo.has("imu"))
    }

    func testAnEmptyAnswerFallsBackFieldByFieldInsteadOfFailing() throws {
        let status: Status = try decode("{}")
        XCTAssertEqual(status.state, "unknown")
        XCTAssertEqual(status.modeCount, 0)
        XCTAssertFalse(status.deviceConnected)
        XCTAssertTrue(status.gestures.isEmpty)
        XCTAssertNil(status.currentLook)
    }

    func testAFieldOfTheWrongTypeCostsThatFieldAndNothingElse() throws {
        let status: Status = try decode(#"{"mode_count": "twelve", "state": "idle"}"#)
        XCTAssertEqual(status.modeCount, 0)
        XCTAssertEqual(status.state, "idle")
    }

    func testGesturesComeFromTheHostRatherThanATableHere() throws {
        let status: Status = try decode(Samples.status)
        XCTAssertEqual(status.gestures,
                       ["short_press", "double_tap", "triple_tap",
                        "tap_4", "tap_5", "long_press"])
        XCTAssertEqual(status.activeModes["short_press"], "Home")
        XCTAssertNil(status.activeModes["triple_tap"])
    }

    func testAGestureThisAppHasNeverHeardOfStillAppears() throws {
        let status: Status = try decode(#"{"active_modes": {"tap_9": "Home", "short_press": null}}"#)
        XCTAssertEqual(status.gestures, ["short_press", "tap_9"])
    }

    func testEventRowsKeepTheNullsTheLogActuallyHas() throws {
        let rows: [EventRow] = try decode(Samples.events)
        XCTAssertEqual(rows.count, 4)
        XCTAssertNil(rows[0].durationS)
        XCTAssertEqual(rows[1].durationS, 1500)
        XCTAssertEqual(rows[1].kind, "mode_exit")
    }
}

final class TimestampTests: XCTestCase {

    func testTheShapesTheLogActuallyWritesAllParse() {
        for text in ["2026-09-06T09:41:12", "2026-09-06 09:41:12",
                     "2026-09-06T09:41:12.250", "2026-09-06T09:41:12Z"] {
            XCTAssertNotNil(Timestamps.parse(text), text)
        }
    }

    func testAnUnreadableTimestampIsNilRatherThanAWrongDate() {
        XCTAssertNil(Timestamps.parse(""))
        XCTAssertNil(Timestamps.parse("last Tuesday"))
    }
}
