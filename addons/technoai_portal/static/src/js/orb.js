/* The landing page's 3D network orb, ported from the Task Hub (CyberOrb3D) without React. */
(function () {
    "use strict";
    const container = document.getElementById("portal-orb");
    const canvas = container && container.querySelector("canvas");
    const ctx = canvas && canvas.getContext("2d");
    if (!ctx) {
        return;
    }
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let animationFrameId = 0;
    let visible = true;
    let width = (canvas.width = 460);
    let height = (canvas.height = 460);

    const updateDimensions = () => {
        const rect = container.getBoundingClientRect();
        const size = Math.min(Math.max(rect.width, 280), 480);
        width = canvas.width = size;
        height = canvas.height = size;
    };
    updateDimensions();
    window.addEventListener("resize", updateDimensions);

    // golden spiral distribution on a sphere
    const points = [];
    const sphereRadius = width * 0.36;
    const totalPoints = 64;
    const colors = ["#9fe7e7", "#289fb7", "#5eead4", "#146b8c"];
    for (let i = 0; i < totalPoints; i++) {
        const phi = Math.acos(1 - (2 * (i + 0.5)) / totalPoints);
        const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 0.5);
        points.push({
            x: sphereRadius * Math.sin(phi) * Math.cos(theta),
            y: sphereRadius * Math.cos(phi),
            z: sphereRadius * Math.sin(phi) * Math.sin(theta),
            radius: Math.random() * 2 + 1.8,
            color: colors[i % colors.length],
        });
    }

    let angleX = 0.002;
    let angleY = 0.004;
    let targetAngleX = 0.003;
    let targetAngleY = 0.005;

    container.addEventListener("mousemove", (e) => {
        if (motion.matches) {
            return;
        }
        const rect = container.getBoundingClientRect();
        targetAngleY = ((e.clientX - rect.left) / rect.width - 0.5) * 0.02;
        targetAngleX = -((e.clientY - rect.top) / rect.height - 0.5) * 0.02;
    });

    let time = 0;
    const render = () => {
        animationFrameId = 0;
        time += 0.02;
        ctx.clearRect(0, 0, width, height);
        angleX += (targetAngleX - angleX) * 0.05;
        angleY += (targetAngleY - angleY) * 0.05;
        const cosX = Math.cos(angleX);
        const sinX = Math.sin(angleX);
        const cosY = Math.cos(angleY);
        const sinY = Math.sin(angleY);
        const cx = width / 2;
        const cy = height / 2;
        const fov = 340;

        const projected = points.map((p) => {
            const x1 = p.x * cosY - p.z * sinY;
            const z1 = p.z * cosY + p.x * sinY;
            const y2 = p.y * cosX - z1 * sinX;
            const z2 = z1 * cosX + p.y * sinX;
            p.x = x1;
            p.y = y2;
            p.z = z2;
            const scale = fov / (fov + z2 + sphereRadius);
            const alpha = Math.max(0.12, Math.min(1, (z2 + sphereRadius) / (sphereRadius * 2)));
            return { px: cx + x1 * scale, py: cy + y2 * scale, pz: z2, alpha, color: p.color, radius: p.radius * scale };
        });
        projected.sort((a, b) => a.pz - b.pz);

        // neural network lines
        for (let i = 0; i < projected.length; i++) {
            for (let j = i + 1; j < projected.length; j++) {
                const dx = projected[i].px - projected[j].px;
                const dy = projected[i].py - projected[j].py;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < width * 0.18) {
                    const lineAlpha = (1 - dist / (width * 0.18)) * 0.22 * Math.min(projected[i].alpha, projected[j].alpha);
                    ctx.beginPath();
                    ctx.strokeStyle = `rgba(40, 159, 183, ${lineAlpha})`;
                    ctx.lineWidth = 1;
                    ctx.moveTo(projected[i].px, projected[i].py);
                    ctx.lineTo(projected[j].px, projected[j].py);
                    ctx.stroke();
                }
            }
        }

        // orbit rings
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(time * 0.15);
        ctx.beginPath();
        ctx.ellipse(0, 0, sphereRadius * 1.25, sphereRadius * 0.38, Math.PI / 4, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(159, 231, 231, 0.25)";
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 6]);
        ctx.stroke();
        ctx.restore();

        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(-time * 0.1);
        ctx.beginPath();
        ctx.ellipse(0, 0, sphereRadius * 1.35, sphereRadius * 0.28, -Math.PI / 5, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(40, 159, 183, 0.2)";
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.restore();

        // points with glow
        projected.forEach((p) => {
            const glowRadius = Math.max(1, p.radius * 2.2);
            const grad = ctx.createRadialGradient(p.px, p.py, 0, p.px, p.py, glowRadius);
            grad.addColorStop(0, p.color);
            grad.addColorStop(1, "rgba(10, 17, 20, 0)");
            ctx.beginPath();
            ctx.fillStyle = grad;
            ctx.arc(p.px, p.py, glowRadius, 0, Math.PI * 2);
            ctx.fill();
            ctx.beginPath();
            ctx.fillStyle = `rgba(255, 255, 255, ${p.alpha})`;
            ctx.arc(p.px, p.py, Math.max(0.8, p.radius * 0.7), 0, Math.PI * 2);
            ctx.fill();
        });

        if (visible && !motion.matches && document.visibilityState === "visible") {
            animationFrameId = requestAnimationFrame(render);
        }
    };

    const refresh = () => {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = 0;
        if (visible && document.visibilityState === "visible") {
            render();
        }
    };
    new IntersectionObserver(([entry]) => {
        visible = entry.isIntersecting;
        refresh();
    }).observe(container);
    motion.addEventListener("change", refresh);
    document.addEventListener("visibilitychange", refresh);

    // the header menu closes with Escape or when focus leaves it, like on the Task Hub
    const nav = document.querySelector(".hub-navigation");
    if (nav) {
        nav.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                nav.open = false;
                nav.querySelector("summary").focus();
            }
        });
        nav.addEventListener("focusout", (event) => {
            if (!nav.contains(event.relatedTarget)) {
                nav.open = false;
            }
        });
    }
    render();
})();
