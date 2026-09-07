import XCTest
@testable import ButtonKit

final class AddressTests: XCTestCase {

    func testTheThingsAPersonActuallyTypesAllReachTheSameService() {
        let expected = "http://192.168.1.20:8080"
        for typed in ["192.168.1.20", " 192.168.1.20 ", "192.168.1.20:8080",
                      "http://192.168.1.20", "http://192.168.1.20:8080/"] {
            XCTAssertEqual(HostAddress.url(from: typed)?.absoluteString, expected, typed)
        }
    }

    func testAPastedPageIsTreatedAsItsAddress() {
        XCTAssertEqual(HostAddress.url(from: "http://desk.local:8080/#events")?.absoluteString,
                       "http://desk.local:8080")
    }

    func testNonsenseIsRefusedBeforeARequestIsMade() {
        XCTAssertNil(HostAddress.url(from: ""))
        XCTAssertNil(HostAddress.url(from: "   "))
    }

    func testARouteTemplateFillsIn() {
        XCTAssertEqual(HostRoute.path(HostRoute.trigger, ["trigger": "double_tap"]),
                       "/api/trigger/double_tap")
    }
}
