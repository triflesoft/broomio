def _get_coro_stack_frames(coro):
    stack_frames = []

    while True:
        cr_frame = getattr(coro, 'cr_frame', None)

        if not cr_frame:
            break

        stack_frames.append(cr_frame)
        coro = getattr(coro, 'cr_await', None)

    return stack_frames
