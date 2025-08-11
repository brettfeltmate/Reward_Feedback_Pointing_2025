# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

import klibs
from klibs import P
from klibs.KLAudio import Tone
from klibs.KLExceptions import TrialException
from klibs.KLGraphics import KLDraw as kld
from klibs.KLConstants import STROKE_INNER
from klibs.KLCommunication import message
from klibs.KLGraphics import fill, flip, blit, clear
from klibs.KLUserInterface import (
    key_pressed,
    pump,
    ui_request,
    get_clicks,
    mouse_pos,
    smart_sleep
)
from klibs.KLBoundary import BoundarySet, CircleBoundary, RectangleBoundary
from klibs.KLTime import CountDown

from math import trunc
from random import randrange

from pyfirmata import serial
from get_key_state import get_key_state  # type: ignore[import]

# Arduino trigger values (for PLATO goggles)
OPEN = b'55'
CLOSE = b'56'

# fixation and rectangle are placed
OFFSET = 21  # cms above screen bottom (horizontally centered)

# Stimulus sizes
UNIT = 9  # 9 mm; converted to px at runtime
CIRCLE_DIAM = 2  # this & rest are multiples of UNIT
RECT_WIDTH = 13
RECT_HEIGHT = 9
FIX_WIDTH = 2
THICKNESS = 0.05  # thickness of stimulus [out]lines

# Colors
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
WHITE = (255, 255, 255, 255)
PURPLE = (255, 0, 255, 255)

# Color-outcome mappings
PENALTY_OUTLINE = RED
PENALTY_FILL = RED
REWARD_OUTLINE = GREEN
REWARD_FILL = None

# Point values
REWARD_PAYOUT = 100
PENALTY_PAYOUT = -600
VENN_PAYOUT = -500
MISS_PAYOUT = 0
TIMEOUT_PAYOUT = -700
# TODO: Need to change payout logic accordingly

# Simulus onset asynchronies
RECT_ONSET = 1000  # fix (immediate) -> rect
CIRC_ONSET = 500  # rect -> circles
PREVIEW_WINDOW = 300   # circle onset -> go signal
TIMEOUT_AFTER = 650  # circles -> (no) response

class reward_feedback_pointing_2025(klibs.Experiment):
    def setup(self):

        if P.condition is None:
            raise ValueError(
                'Initial condition (reward, vision) must be specified at runtime\n'
                'using the condition flag (e.g. klibs run 24 -c vision).'
            )
        # Handles communication with arduino (goggles)
        self.goggles = serial.Serial(port='COM6', baudrate=9600)

        # Go-signal
        self.go_tone = Tone(100)

        #
        #   Set up visual properties
        #

        # Get px per mm
        self.unit = (P.ppi / 25.4) * UNIT
        self.offset = self.unit * OFFSET
        self.rect_w = self.unit * RECT_WIDTH
        self.rect_he = self.unit * RECT_HEIGHT
        self.circle_d = self.unit * CIRCLE_DIAM
        self.fix_w = self.unit * FIX_WIDTH
        self.thick = self.unit * THICKNESS

        # Define stimuli
        self.stimuli = {
            'fix': kld.FixationCross(
                size=self.fix_w, thickness=self.thick, fill=WHITE
            ),
            'rect': kld.Rectangle(
                width=self.rect_w,
                height=self.rect_he,
                stroke=[self.thick, BLUE, STROKE_INNER],
            ),
            'reward': kld.Circle(
                diameter=self.circle_d,
                fill=REWARD_FILL,
                stroke=[self.thick, REWARD_OUTLINE, STROKE_INNER],
            ),
            'penalty': kld.Circle(
                diameter=self.circle_d,
                fill=PENALTY_FILL,
                stroke=[self.thick, PENALTY_OUTLINE, STROKE_INNER],
            ),
            'endpoint': kld.Asterisk(
                size=self.circle_d // 3, thickness=self.thick * 2, fill=WHITE
            ),
        }

        self.bs = BoundarySet()
        self.bs.add_boundary(
            RectangleBoundary(
                label='rect',
                p1=(
                    (P.screen_x / 2) + (self.rect_w / 2),  # type: ignore[operator]
                    (P.screen_y - self.offset) - (self.rect_he / 2),  # type: ignore[operator]
                ),
                p2=(
                    (P.screen_x / 2) - (self.rect_w / 2),  # type: ignore[operator]
                    (P.screen_y - self.offset) + (self.rect_he / 2),  # type: ignore[operator]
                ),
            )
        )

        #
        #   Set up condition order
        #

        self.conditions = (
            ['vision', 'reward']
            if P.condition == 'vision'
            else ['reward', 'vision']
        )

        self.conditions = [cond for cond in self.conditions for _ in range(3)]

        if P.run_practice_blocks:
            self.insert_practice_block(
                block_nums=[1],
                trial_counts=P.trials_per_practice_block,  # type: ignore[attr-defined]
            )

        #
        #   Instruction set
        #

        self.instructions = {
            'reward': (
                'When you initiate your movement, the goggles will close, and you will not see the target or where you landed.'
                '\n\n'
                'The goggles will re-open at the end of the trial and you will see your points gained/lost on the trial,'
                '\n'
                'as well as your cumulative points so far.'
                '\n\n'
                f'You will complete {P.blocks_per_experiment * P.trials_per_block // 2} trials of this condition; you may take a break in between trials whenever you need.'
            ),
            'vision': (
                'You will be able to see the target and where you land,'
                '\n'
                'however you will not see how many points you gained/lost on the trial nor your cumulative points so far.'
                '\n\n'
                f'You will complete {P.blocks_per_experiment * P.trials_per_block // 2} trials of this condition; you may take a break in between trials whenever you need.'
            ),
        }

    def block(self):
        self.goggles.write(OPEN)

        # get task condition for block
        if P.practicing:
            self.condition = 'practice'
        else:
            self.condition = self.conditions.pop(0)

        self.bank = 0

        instrux = '(PRACTICE BLOCK)\n' if P.practicing else '(TESTING BLOCK)\n'

        if not P.practicing:
            instrux += self.instructions[self.condition]

        instrux += '\n\nPress spacebar to begin.\nTrials are started by pressing/holding F6.'

        # Present instructions
        fill()
        message(text=instrux, location=P.screen_c, blit_txt=True)
        flip()

        # Wait for spacebar press to start running trials
        while True:
            # Monitor for any commands to quit, etc
            q = pump(True)
            _ = ui_request(queue=q)
            if key_pressed('space'):
                break

    def trial_prep(self):
        self.goggles.write(OPEN)
        # determine circle positions
        self.positions = self.get_circle_placements()

        # register corresponding touch boundaries
        self.bs.add_boundaries(
            [
                CircleBoundary(
                    'penalty', self.positions['penalty'], self.circle_d / 2
                ),
                CircleBoundary(
                    'reward', self.positions['reward'], self.circle_d / 2
                ),
            ]
        )

        # practice trial have "no" timeout, but code is cleaner if made excessively long instead
        trial_timeout = (
            TIMEOUT_AFTER if not P.practicing else 30000
        )  # 30s when practicing

        # register event timings
        self.evm.add_event('rect_onset', RECT_ONSET)
        self.evm.add_event('circle_onset', CIRC_ONSET, after='rect_onset')
        self.evm.add_event('go_signal', PREVIEW_WINDOW, after='circle_onset')
        self.evm.add_event('trial_timeout', trial_timeout, after='go_signal')

        # present fix and wait for button press to begin
        self.draw_display(fix=True)

        while not key_pressed('F6'):
            q = pump(True)
            _ = ui_request(queue=q)

    def trial(self):  # type: ignore[override]

        if P.development_mode:
            mouse_pos(position=(P.screen_x // 2, P.screen_y))  # type: ignore[operator]

        # Monitor for and admonish premature movements
        while self.evm.before('go_signal'):
            q = pump(True)
            _ = ui_request(queue=q)

            if get_key_state('F6') == 0:
                self.evm.stop_clock()

                msg = message('Please wait for the tone before moving.')
                self.draw_display(
                    also=(msg, self.bs.boundaries['rect'].center),
                )

                self.wait_for(P.feedback_duration)  # type: ignore[attr-defined]

                raise TrialException('Premptive movement')

            rect_visible, circles_visible = False, False

            # fixed delay before rect presented
            if self.evm.after('rect_onset') and not rect_visible:
                self.draw_display(rect=True)
                rect_visible = True  # don't do redundant redraws

            if (
                self.evm.after('circle_onset')
                and not P.practicing
                and not circles_visible
            ):
                self.draw_display(rect=True, circles=True)
                circles_visible = True

        self.go_tone.play()
        tone_play_time = self.evm.trial_time_ms

        # Response window start #
        rt, mt, clicked_on, clicked_at, pay = None, None, None, None, None
        while self.evm.before('trial_timeout'):

            while rt is None:
                if get_key_state('F6') == 0:
                    rt = self.evm.trial_time_ms - tone_play_time  # type: ignore[operator]

                    # conditionally close goggles at movement start
                    if self.condition == 'reward':
                        self.goggles.write(CLOSE)

            # log touched point, if any 
            clicked_at, clicked_on = self.listen_for_click()

            if clicked_on is not None:
                mt = self.evm.trial_time_ms - rt - tone_play_time  # type: ignore[operator]
                break
        # response window end #

        # Ensure circles have been removed, then return vision
        clear()
        # self.goggles.write(OPEN)

        # determine appropriate payout
        pay = self.get_payout(clicked_on)
        self.bank += pay

        # conditionally display performance feedback
        if clicked_on is not None:

            # only movement time provided on practice trials
            if self.condition == 'practice':
                text = f'Movement time was: {trunc(mt)} ms.'  # type: ignore[operation]

                self.draw_display(
                    rect=True,
                    also=(message(text), self.bs.boundaries['rect'].center),
                )

            # only present earnings (e.g., no visual indication of performance)
            elif self.condition == 'reward':

                smart_sleep(300)
                self.goggles.write(OPEN)

                # earnings for trial
                msg = message(f'Trial payout: {pay}', blit_txt=False)
                self.draw_display(
                    rect=True,
                    also=(msg, self.bs.boundaries['rect'].center),
                )

                self.wait_for(P.feedback_duration)  # type: ignore[attr-defined]

                # current earnings for block
                msg = message(f'Total points: {self.bank}')
                self.draw_display(
                    rect=True,
                    also=(msg, self.bs.boundaries['rect'].center),
                )

            # only present landing point (e.g., no "earnings" in vision condition)
            else:
                self.goggles.write(OPEN)
                # self.draw_display(
                #     rect=True,
                #     circles=True,
                #     also=(self.stimuli['endpoint'], clicked_at),
                # )

        # on failures to complete movement within timeframe
        else:
            msg = message('Trial timed-out!\nNo response was detected!')
            self.draw_display(
                rect=True,
                also=(msg, self.bs.boundaries['rect'].center),
            )

        self.wait_for(P.feedback_duration)  # type: ignore[attr-defined]

        return {
            'practicing': P.practicing,
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'feedback_condition': self.condition,
            'reward_side': self.reward_side,  # type: ignore[defined]
            'reward_x': self.positions['reward'][0],
            'reward_y': self.positions['reward'][1],
            'clicked_on': clicked_on if clicked_on is not None else 'NA',
            'clicked_x': clicked_at[0] if clicked_at is not None else 'NA',
            'clicked_y': clicked_at[1] if clicked_at is not None else 'NA',
            'reaction_time': rt,
            'movement_time': mt,
            'trial_earnings': pay,
            'block_earnings': self.bank,
        }

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass

    def get_payout(self, clicked_on=None):
        if clicked_on is None:
            return TIMEOUT_PAYOUT

        elif clicked_on == 'reward':
            return REWARD_PAYOUT

        elif clicked_on == 'penalty':
            return PENALTY_PAYOUT

        elif clicked_on == 'overlap':
            return VENN_PAYOUT

        elif clicked_on == 'outside':
            return 0

        else:
            return MISS_PAYOUT

    def listen_for_click(self):
        clicks = get_clicks()
        clicked = None

        if len(clicks):
            clicked_reward = self.bs.within_boundary('reward', p=clicks[0])
            clicked_penalty = self.bs.within_boundary('penalty', p=clicks[0])
            clicked_rect = self.bs.within_boundary('rect', p=clicks[0])

            if clicked_rect:
                if clicked_reward and not clicked_penalty:
                    clicked = 'reward'

                elif clicked_penalty and not clicked_reward:
                    clicked = 'penalty'

                elif clicked_reward and clicked_penalty:
                    clicked = 'overlap'

                else:
                    clicked = 'rect'

            else:
                clicked = 'outside'
        else:
            clicks = [[-1, -1]]

        return clicks[0], clicked

    def draw_display(
        self,
        fix: bool = False,
        rect: bool = False,
        circles: bool = False,
        also=None,
    ):

        fill()

        if fix:
            blit(
                self.stimuli['fix'],
                location=self.bs.boundaries['rect'].center,
                registration=5,
            )

        if rect:
            blit(
                self.stimuli['rect'],
                location=self.bs.boundaries['rect'].center,
                registration=5,
            )

        if circles:
            blit(
                self.stimuli['penalty'],
                location=self.positions['penalty'],
                registration=5,
            )
            blit(
                self.stimuli['reward'],
                location=self.positions['reward'],
                registration=5,
            )

        if also:
            blit(also[0], location=also[1], registration=5)

        flip()

    def get_circle_placements(self):
        rad_px = self.circle_d / 2
        circle_offset = 0.5 * rad_px
        padd = self.thick * 2

        rect_p1 = [int(xy) for xy in self.bs.boundaries['rect'].p1]
        rect_p2 = [int(xy) for xy in self.bs.boundaries['rect'].p2]

        origin_x = randrange(
            start=int(rect_p1[0] + (1.5 * rad_px) + padd),
            stop=int(rect_p2[0] - (1.5 * rad_px) - padd),
        )
        origin_y = randrange(
            start=int(rect_p1[1] + rad_px + padd),
            stop=int(rect_p2[1] - rad_px - padd),
        )

        if self.reward_side == 'right':  # type: ignore[attr-defined]
            placements = {
                'penalty': (origin_x - circle_offset, origin_y),
                'reward': (origin_x + circle_offset, origin_y),
            }
        else:
            placements = {
                'reward': (origin_x - circle_offset, origin_y),
                'penalty': (origin_x + circle_offset, origin_y),
            }

        return placements

    def wait_for(self, duration: float):
        wait_period = CountDown(duration)
        while wait_period.counting():
            q = pump(True)
            _ = ui_request(queue=q)
