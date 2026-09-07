import XCTest
@testable import ButtonKit

final class ConfigTests: XCTestCase {

    private func decode<T: Decodable>(_ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    func testConfigReadsTheEffectiveModesAndSaysWhereASaveWouldLand() throws {
        let config: ConfigSnapshot = try decode(Samples.config)
        XCTAssertEqual(config.scene, "desk")
        XCTAssertEqual(config.modes.count, 4)
        XCTAssertEqual(config.modes.first?.name, "Home")
        XCTAssertEqual(config.modes.first?.template, "actions")
        XCTAssertTrue(config.writePath?.hasSuffix("desk.json") ?? false)
    }

    func testAModeOfAnUnknownTemplateStillListsAndStillSaysWhenItRuns() throws {
        let config: ConfigSnapshot = try decode(#"""
        {"effective": {"modes": [
          {"name": "Thing", "template": "something_new",
           "activation": {"type": "schedule", "at": "06:15"},
           "wobble": 3}]}}
        """#)
        let mode = try XCTUnwrap(config.modes.first)
        XCTAssertEqual(mode.template, "something_new")
        XCTAssertEqual(mode.activationSummary, "At 06:15")
        XCTAssertEqual(mode.extras["wobble"]?.summary, "3")
    }

    func testActivationSummariesReadAsSentences() throws {
        let config: ConfigSnapshot = try decode(Samples.config)
        XCTAssertEqual(config.modes[0].activationSummary, "Always on")
        XCTAssertEqual(config.modes[1].activationSummary, "Only when opened")
        XCTAssertEqual(config.modes[2].activationSummary, "At 07:30 Mon Tue Wed Thu Fri")
        XCTAssertEqual(config.modes[3].activationSummary, "Between 09:00-17:00")
    }

    func testAWarningIsCarriedThroughRatherThanSwallowed() throws {
        let config: ConfigSnapshot = try decode(#"""
        {"warnings": ["mode 2: unknown template 'wobble' - using actions"],
         "effective": {"modes": []}}
        """#)
        XCTAssertEqual(config.warnings.count, 1)
    }
}
