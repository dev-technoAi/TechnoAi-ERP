/** The rolling 3D dot terrain behind the apps launcher (same as on the sign-in page). */
export function startTerrain(canvas) {
    const ctx = canvas.getContext("2d");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w, h, t = 0, mx = 0, my = 0, tx = 0, ty = 0, frameId = 0, running = true;
    const size = () => {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        w = canvas.clientWidth;
        h = canvas.clientHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const onMove = (e) => {
        tx = e.clientX / w - 0.5;
        ty = e.clientY / h - 0.5;
    };
    const COLS = 70, ROWS = 42, GAP = 46;
    const frame = () => {
        if (!running) {
            return;
        }
        if (!reduce) {
            t += 0.012;
        }
        mx += (tx - mx) * 0.04;
        my += (ty - my) * 0.04;
        ctx.clearRect(0, 0, w, h);
        const camY = 260 + my * 40, horizon = h * 0.42, f = 520;
        for (let r = ROWS - 1; r >= 0; r--) {
            const z = 120 + r * GAP;
            for (let q = 0; q < COLS; q++) {
                const x = (q - COLS / 2) * GAP - mx * 260;
                const y = Math.sin(q * 0.22 + t * 2) * 26 + Math.cos(r * 0.28 + t * 1.4) * 22;
                const s = f / z, px = w / 2 + x * s, py = horizon + (camY - y) * s * 0.55;
                if (px < -20 || px > w + 20 || py > h + 20) {
                    continue;
                }
                const near = 1 - r / ROWS, lift = (y + 48) / 96;
                ctx.fillStyle = `rgba(${Math.round(40 + 119 * lift)}, ${Math.round(159 + 72 * lift)}, ${Math.round(183 + 48 * lift)}, ${0.06 + near * 0.38})`;
                ctx.beginPath();
                ctx.arc(px, py, Math.max(0.6, 1.8 * s), 0, Math.PI * 2);
                ctx.fill();
            }
        }
        if (!reduce) {
            frameId = requestAnimationFrame(frame);
        }
    };
    size();
    window.addEventListener("resize", size);
    window.addEventListener("mousemove", onMove);
    frame();
    return () => {
        running = false;
        cancelAnimationFrame(frameId);
        window.removeEventListener("resize", size);
        window.removeEventListener("mousemove", onMove);
    };
}
