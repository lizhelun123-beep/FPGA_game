"""OpenCV game canvas. All vertices come from the models passed to C physics."""
import cv2
import numpy as np

COLORS = {"SOURCE": (187, 112, 255), "MIRROR": (112, 225, 250),
          "WALL": (145, 154, 165), "TARGET": (136, 230, 93),
          "PORTAL_A": (249, 184, 81), "PORTAL_B": (71, 161, 255)}
BUTTONS = ("Start/Pause", "Lock", "Unlock", "Reset", "Calibrate", "Previous", "Next", "Snapshot")


class GameView:
    def __init__(self, width=1280, height=900):
        self.width, self.height = width, height
        self.buttons = [(name, (24+i*154, 80, 164+i*154, 118)) for i, name in enumerate(BUTTONS)]

    def action_at(self, x, y):
        return next((name for name, (x0, y0, x1, y1) in self.buttons
                     if x0 <= x <= x1 and y0 <= y <= y1), None)

    @staticmethod
    def text(canvas, text, point, size=.55, color=(215, 225, 238)):
        cv2.putText(canvas, str(text), point, cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)

    def render(self, controller, source_status, now, name="", note="", telemetry=None):
        image = np.full((self.height, self.width, 3), (27, 20, 16), np.uint8)
        stale = controller.display_stale(now)
        status = "DISCONNECTED" if source_status == "DISCONNECTED" else controller.status(now)
        if source_status in ("LIVE", "STALE", "DISCONNECTED"):
            source_status = status
        self.text(image, "LIGHT LAB  /  SCENE GAME", (24, 33), .85, (248, 231, 205))
        mode = "LOCKED" if controller.locked else ("PAUSED" if controller.paused else "RUNNING")
        calibrated = controller.mapper.calibration is not None
        mapping = "CALIBRATED / mm" if calibrated else "UNCALIBRATED PREVIEW / no real-world scale"
        self.text(image, f"{mapping}   |   {mode}   |   {status}", (24, 59), .5,
                  (132, 215, 128) if calibrated else (80, 191, 255))
        for label, (x0, y0, x1, y1) in self.buttons:
            cv2.rectangle(image, (x0, y0), (x1, y1), (68, 57, 44), -1)
            self.text(image, label, (x0+9, y0+25), .5)
        mapper = controller.mapper
        scale = min((self.width-72)/mapper.width, (self.height-260)/mapper.height)
        ox = (self.width-mapper.width*scale)/2
        oy = 143+(self.height-260-mapper.height*scale)/2

        def pixel(point):
            return tuple(np.rint(np.asarray(point)*scale+(ox, oy)).astype(int))

        def polygon(points):
            return np.asarray([pixel(p) for p in points], np.int32)

        x0, y0 = pixel((0, 0))
        x1, y1 = pixel((mapper.width, mapper.height))
        cv2.rectangle(image, (x0, y0), (x1, y1), (40, 33, 27), -1)
        step = max(mapper.width, mapper.height)/20
        for x in np.arange(0, mapper.width, step):
            cv2.line(image, pixel((x, 0)), pixel((x, mapper.height)), (48, 41, 35), 1)
        for y in np.arange(0, mapper.height, step):
            cv2.line(image, pixel((0, y)), pixel((mapper.width, y)), (48, 41, 35), 1)
        cv2.rectangle(image, (x0, y0), (x1, y1), (100, 106, 87), 1)
        if stale and controller.display:
            self.text(image, "STALE / LAST OBSERVATION", (x0+12, y0+25), .6, (80, 191, 255))
        for model in controller.display:
            color = COLORS[model.type]
            if stale or model.held:
                color = tuple(c//2 for c in color)
            center = pixel(model.center)
            if model.type == "TARGET":
                radius = max(1, round(model.size[0]*scale/2))
                cv2.circle(image, center, radius, color, -1, cv2.LINE_AA)
                cv2.circle(image, center, round(radius*.55), (20, 32, 17) if stale else (40, 65, 35), 2, cv2.LINE_AA)
            elif model.type == "MIRROR":
                a, b = (pixel(p) for p in model.mirror_endpoints())
                cv2.line(image, a, b, color, max(2, round(model.size[1]*scale)), cv2.LINE_AA)
                cv2.line(image, a, b, (125, 125, 125) if stale else (250, 251, 250), 2, cv2.LINE_AA)
            else:
                corners = polygon(model.vertices())
                cv2.fillConvexPoly(image, corners, tuple(c//3 for c in color), cv2.LINE_AA)
                cv2.polylines(image, [corners], True, color, 2, cv2.LINE_AA)
                if model.type.startswith("PORTAL"):
                    offset = np.asarray(model.axis)*model.size[0]*.35
                    # Solid -> ring is the directed longitudinal axis used by C.
                    cv2.circle(image, pixel(np.asarray(model.center)-offset), 5, color, -1, cv2.LINE_AA)
                    cv2.circle(image, pixel(np.asarray(model.center)+offset), 7, color, 2, cv2.LINE_AA)
                elif model.type == "SOURCE" and model.direction_valid:
                    cv2.arrowedLine(image, center, pixel(model.source_tip), color, 2, cv2.LINE_AA, tipLength=.3)
            suffix = " held" if model.held else (" axis?" if model.type == "SOURCE" and not model.direction_valid else "")
            self.text(image, f"{model.type} {model.confidence}%" + suffix,
                      (center[0]+8, center[1]-12), .4, color)
        for x, y, ex, ey in controller.ray["segments"]:
            start, end = pixel((x, y)), pixel((ex, ey))
            cv2.line(image, start, end, (22, 31, 35), 7, cv2.LINE_AA)
            cv2.line(image, start, end, (65, 112, 127) if stale else (42, 225, 255), 3, cv2.LINE_AA)
        if controller.ray["success"] and not stale and not (controller.paused or controller.locked):
            self.text(image, "TARGET REACHED", (self.width-260, 33), .75, COLORS["TARGET"])
        age = "still photo" if controller.persistent else (
            "--" if controller.age(now) is None else f"{controller.age(now):.2f}s")
        if telemetry is not None:
            # The reader may already hold a newer scene the UI has not adopted.
            # Geometry age belongs to the accepted usable scene, not that packet.
            source_status = status + f" {telemetry['hz']:.1f} Hz RX"
        if ((controller.paused or controller.locked) and not controller.display_persistent and
                controller.display_received is not None):
            age += f" / view {max(0, now-controller.display_received):.2f}s"
        rx_frame = telemetry["frame"] if telemetry is not None else controller.frame
        self.text(image, f"INPUT {source_status}  |  {name[:24]}  |  frame RX={rx_frame} view={controller.display_frame}  |  valid age={age}",
                  (24, self.height-94), .48)
        self.text(image, f"{controller.reason}  |  objects={len(controller.display)}  |  ray={controller.ray['termination']}  |  hits={','.join(controller.ray['hits']) or '-'}",
                  (24, self.height-69), .5)
        self.text(image, note or "Mouse buttons above. Space pause / L lock / U unlock / R reset / C calibrate / arrows browse / S save / Q quit",
                  (24, self.height-43), .45)
        x = 24
        for kind, color in COLORS.items():
            cv2.circle(image, (x+5, self.height-17), 4, color, -1)
            self.text(image, kind, (x+16, self.height-12), .4, color)
            x += 170
        return image
