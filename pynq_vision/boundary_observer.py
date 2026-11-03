"""Read the passive CSI1.3 boundary observer through the existing CSI owner.

The indexed words are part of the same coherent publication as packet/CRC
counters. No DMA register, image buffer, reset or error-clear access belongs
here. A software freeze records the state after the fault was detected; it is
not a claim that software sampled the exact cycle of a VDMA error.
"""
import time


OBSERVER_VERSION = 0x00010003
OBSERVER_MAGIC = 0x42564F31
WORD_COUNT = 24
ARM = 1 << 30
FREEZE = 1 << 31


def _stream(words, pixels_per_beat, expected_beats, fault_mask):
    names = ('accepted_sofs', 'accepted_eols', 'current_frame_eols',
             'current_line_beats', 'last_line_beats', 'last_frame_eols',
             'min_line_beats', 'max_line_beats')
    result = dict(zip(names, words))
    partial_sof = bool(fault_mask & (1 << 2))
    result.update(pixels_per_beat=pixels_per_beat,
                  expected_beats_per_line=expected_beats,
                  expected_lines_per_frame=720,
                  beat_unit='accepted TVALID and TREADY transfer',
                  current_frame_index=words[0] if words[0] else None,
                  last_completed_frame_index=words[0] - 1 if words[0] >= 2 else None,
                  frame_index_unit='independent accepted-SOF sequence modulo 2^32 within arm epoch',
                  last_line_terminated=False if partial_sof else bool(words[1]),
                  last_line_beats_meaning=(
                      'unterminated line before accepted SOF' if partial_sof else
                      'most recent accepted TLAST line' if words[1] else
                      'no accepted TLAST line'),
                  last_line_pixels=words[4] * pixels_per_beat)
    if not words[1]:
        result['min_line_beats'] = result['max_line_beats'] = None
    return result


def decode_words(words):
    """Decode a complete publication, retaining all raw words for evidence."""
    if len(words) != WORD_COUNT or any(type(w) is not int or not 0 <= w <= 0xFFFFFFFF
                                       for w in words):
        raise RuntimeError('invalid boundary observer word set')
    if words[0] != OBSERVER_MAGIC:
        raise RuntimeError('boundary observer ABI magic mismatch')
    flags, reason = words[1:3]
    frozen = bool(flags & 1)
    return {
        'abi': 'CSI1.3_BOUNDARY_V1', 'raw_words': list(words),
        'armed': bool(flags & 2), 'frozen': frozen,
        'first_reason': reason,
        'csi_error_mask': reason & 0xFF,
        'vdma_error_mask': (reason >> 8) & 0xFF,
        'overflow': bool(reason & (1 << 16)),
        'freeze_origin': ('software_after_fault' if reason & FREEZE else
                          'first_observer_fault') if frozen else 'live',
        'freeze_time_semantics': (
            'source-domain capture after software detected a fault; not the exact VDMA error cycle'
            if reason & FREEZE else
            'first passive observer fault edge; not proof of the exact VDMA error cycle'
            if frozen else 'current source-domain observer state'),
        'frame_alignment': (
            'CSI and VDMA have independent accepted-SOF sequences in the same arm epoch; '
            'align by sequence, not snapshot time. Pipeline latency may put the taps in different frames.'),
        'video_tick': words[3],
        'video_tick_unit': 'video_aclk cycles modulo 2^32; not exposure time',
        'accepted_fs': words[4], 'accepted_fe': words[5],
        'arm_sequence': words[6], 'raw_strobes': words[7],
        'csi_output': _stream(words[8:16], 4, 320, reason & 0xFF),
        'vdma_input': _stream(words[16:24], 1, 1280, (reason >> 8) & 0xFF),
    }


class BoundaryObserver:
    """Use an already owned RegisterBlock; this class acquires no device."""
    def __init__(self, regs):
        self.regs = regs

    def _require_version(self):
        version = self.regs.read(0x0C)
        if version != OBSERVER_VERSION:
            raise RuntimeError('CSI1.3 boundary observer is required; got 0x{:08x}'.format(version))

    @staticmethod
    def _deadline(timeout):
        if not 0 < timeout <= 0.1:
            raise ValueError('boundary observer timeout must be in (0, 0.1] seconds')
        return time.monotonic() + timeout

    def _snapshot(self, deadline):
        self._require_version()
        if time.monotonic() >= deadline or self.regs.read(0x14) & 1:
            raise RuntimeError('boundary observer requires an idle snapshot interface')
        sequence = self.regs.read(0x10)
        expected = (sequence + 1) & 0xFFFFFFFF
        self.regs.write(0x10, 1)
        for _ in range(1001):
            if not self.regs.read(0x14) & 1 and self.regs.read(0x10) == expected:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('boundary snapshot handshake timed out')
            time.sleep(0.0001)
        else:
            raise RuntimeError('boundary snapshot handshake poll budget exhausted')
        words = []
        for index in range(WORD_COUNT):
            if time.monotonic() >= deadline:
                raise RuntimeError('boundary snapshot word read timed out')
            self.regs.write(0x18, index)
            if self.regs.read(0x18) & 0xFF != index:
                raise RuntimeError('boundary observer index did not latch')
            words.append(self.regs.read(0x1C))
        result = decode_words(words)
        result.update(control=self.regs.read(0x00),
                      long_packets=self.regs.read(0x04),
                      crc_errors=self.regs.read(0x08),
                      packet_crc_scope=('coherent publication time; boundary words may retain '
                                        'an earlier first-fault latch'),
                      version=OBSERVER_VERSION, snapshot_sequence=expected)
        if self.regs.read(0x10) != expected or self.regs.read(0x14) & 1:
            raise RuntimeError('boundary snapshot changed during read')
        return result

    def snapshot(self, timeout=0.1):
        return self._snapshot(self._deadline(timeout))

    def arm(self, timeout=0.1):
        """Arm once before capture; confirm the source-domain epoch changed."""
        deadline = self._deadline(timeout)
        before = self._snapshot(deadline)
        expected = (before['arm_sequence'] + 1) & 0xFFFFFFFF
        self.regs.write(0x18, ARM)
        for _ in range(1001):
            result = self._snapshot(deadline)
            if result['arm_sequence'] == expected:
                if not result['armed'] or result['frozen'] or result['first_reason']:
                    raise RuntimeError('boundary observer did not arm cleanly')
                return result
            if result['arm_sequence'] != before['arm_sequence']:
                raise RuntimeError('boundary observer arm sequence changed unexpectedly')
            if time.monotonic() >= deadline:
                break
            time.sleep(0.0001)
        raise RuntimeError('boundary observer arm was not acknowledged')

    def freeze(self, timeout=0.1):
        """Keep an existing hardware first fault or request one software freeze."""
        deadline = self._deadline(timeout)
        before = self._snapshot(deadline)
        if before['frozen']:
            return before
        if not before['armed']:
            raise RuntimeError('boundary observer was not armed')
        self.regs.write(0x18, FREEZE)
        for _ in range(1001):
            result = self._snapshot(deadline)
            if result['arm_sequence'] != before['arm_sequence']:
                raise RuntimeError('boundary observer rearmed during fault capture')
            if result['frozen']:
                return result
            if time.monotonic() >= deadline:
                break
            time.sleep(0.0001)
        raise RuntimeError('boundary observer freeze was not acknowledged')
