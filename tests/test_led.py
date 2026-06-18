import asyncio

from aibutton.led import LEDController, LEDState


async def test_state_switching_cancels_previous_task(mock_pins):
    led = LEDController()
    led.set_state(LEDState.IDLE)
    idle_task = led._task
    await asyncio.sleep(0.12)  # let a few frames render
    assert not idle_task.done()

    led.set_state(LEDState.THINKING)
    await asyncio.sleep(0.12)
    assert idle_task.cancelled()
    assert not led._task.done()
    led.close()


async def test_solid_states_set_expected_color(mock_pins):
    led = LEDController()
    led.set_state(LEDState.LISTENING)
    await asyncio.sleep(0.05)
    assert tuple(led._led.color) == (1, 1, 0)

    led.set_state(LEDState.SUCCESS)
    await asyncio.sleep(0.05)
    assert tuple(led._led.color) == (0, 1, 0)
    led.close()


async def test_thinking_is_a_rotating_rainbow(mock_pins):
    led = LEDController()
    led.set_state(LEDState.THINKING)
    await asyncio.sleep(0.05)
    first = tuple(led._led.color)
    # Full saturation/value -> a vivid colour: at least one channel near full.
    assert max(first) > 0.9
    # The hue rotates (~1 s/turn), so the colour changes over time.
    await asyncio.sleep(0.3)
    later = tuple(led._led.color)
    assert later != first
    # ...and it keeps going (never auto-returns to idle blue).
    await asyncio.sleep(0.3)
    r, g, b = led._led.color
    assert not (r == 0 and g == 0)  # not the idle blue-only breathe
    led.close()


async def test_error_flashes_then_breathes(mock_pins):
    led = LEDController()
    led.set_state(LEDState.ERROR)
    await asyncio.sleep(0.05)
    assert tuple(led._led.color) == (1, 0, 0)  # first flash on
    # after 3 on/off flashes (1.2 s) it falls into the blue breathe
    await asyncio.sleep(1.4)
    r, g, b = led._led.color
    assert r == 0 and g == 0  # only blue channel active
    led.close()


async def test_alert_flashes_red_white_until_state_changes(mock_pins):
    led = LEDController()
    led.set_state(LEDState.ALERT)
    await asyncio.sleep(0.05)
    assert tuple(led._led.color) == (1, 0, 0)
    await asyncio.sleep(0.2)
    assert tuple(led._led.color) == (1, 1, 1)

    # unlike ERROR, ALERT never auto-returns to idle
    await asyncio.sleep(1.0)
    assert tuple(led._led.color) in ((1, 0, 0), (1, 1, 1))

    led.set_state(LEDState.IDLE)
    await asyncio.sleep(0.05)
    r, g, b = led._led.color
    assert r == 0 and g == 0  # blue breathe
    led.close()


async def test_close_stops_animation(mock_pins):
    led = LEDController()
    led.set_state(LEDState.IDLE)
    task = led._task
    led.close()
    await asyncio.sleep(0.01)
    assert task.cancelled()


async def test_timing_pulses_teal_until_state_changes(mock_pins):
    led = LEDController()
    led.set_state(LEDState.TIMING)
    await asyncio.sleep(0.15)  # let a few frames render without error
    assert not led._task.done()  # never auto-returns to idle while timing
    # The cyan pulse drives the green/blue channels (no red), unlike IDLE's
    # blue-only breathe and ALERT's red flashes.
    seen_green_or_blue = False
    for _ in range(8):
        r, g, b = led._led.color
        assert r == 0  # cyan: no red channel
        if g > 0.05 or b > 0.05:
            seen_green_or_blue = True
        await asyncio.sleep(0.05)
    assert seen_green_or_blue
    led.set_state(LEDState.IDLE)
    await asyncio.sleep(0.05)
    led.close()


async def test_off_is_dark_until_state_changes(mock_pins):
    led = LEDController()
    led.set_state(LEDState.OFF)
    await asyncio.sleep(0.1)
    assert tuple(led._led.color) == (0, 0, 0)  # fully dark
    assert not led._task.done()  # held until woken
    led.set_state(LEDState.IDLE)
    await asyncio.sleep(0.05)
    led.close()


async def test_pomodoro_work_breathes_amber(mock_pins):
    led = LEDController()
    led.set_state(LEDState.POMODORO_WORK)
    await asyncio.sleep(0.15)
    assert not led._task.done()
    # amber: red + green channels lit, never blue
    seen_lit = False
    for _ in range(8):
        r, g, b = led._led.color
        assert b == 0  # no blue, unlike IDLE/TIMING/COUNTING
        if r > 0.05 and g > 0.02:
            seen_lit = True
        await asyncio.sleep(0.05)
    assert seen_lit
    led.set_state(LEDState.IDLE)
    await asyncio.sleep(0.05)
    led.close()


async def test_pomodoro_break_breathes_green(mock_pins):
    led = LEDController()
    led.set_state(LEDState.POMODORO_BREAK)
    await asyncio.sleep(0.15)
    assert not led._task.done()
    seen_lit = False
    for _ in range(8):
        r, g, b = led._led.color
        assert r == 0 and b == 0  # green-only breathe
        if g > 0.05:
            seen_lit = True
        await asyncio.sleep(0.05)
    assert seen_lit
    led.set_state(LEDState.IDLE)
    await asyncio.sleep(0.05)
    led.close()


async def test_pomodoro_paused_is_dim_amber(mock_pins):
    led = LEDController()
    led.set_state(LEDState.POMODORO_PAUSED)
    await asyncio.sleep(0.15)
    assert not led._task.done()
    seen_lit = False
    peak = 0.0
    for _ in range(10):
        r, g, b = led._led.color
        assert b == 0  # amber: no blue
        if r > 0.01:
            seen_lit = True
        peak = max(peak, r)
        await asyncio.sleep(0.05)
    assert seen_lit
    assert peak < 0.5  # clearly dimmer than the active work breathe (~1.0)
    led.set_state(LEDState.IDLE)
    await asyncio.sleep(0.05)
    led.close()


async def test_counting_breathes_magenta_until_state_changes(mock_pins):
    led = LEDController()
    led.set_state(LEDState.COUNTING)
    await asyncio.sleep(0.15)
    assert not led._task.done()  # held until the counter exits
    # Magenta breathe drives red + blue, never green.
    seen_lit = False
    for _ in range(8):
        r, g, b = led._led.color
        assert g == 0  # magenta: no green channel
        if r > 0.05 or b > 0.05:
            seen_lit = True
        await asyncio.sleep(0.05)
    assert seen_lit
    led.set_state(LEDState.IDLE)
    await asyncio.sleep(0.05)
    led.close()
