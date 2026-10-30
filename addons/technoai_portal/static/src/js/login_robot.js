/* Sign-in page: the Techno AI robot that reacts to the form, and the 3D dot-terrain background. */
(function () {
    "use strict";
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ---------------------------------------------------------------- robot
    const bot = document.getElementById("o_tai_bot");
    const bubble = document.getElementById("o_tai_bubble");
    if (bot && bubble) {
        const eyes = document.getElementById("o_tai_eyes");
        const mouth = document.getElementById("o_tai_mouth");
        const email = document.querySelector("input[name=login]");
        const pw = document.querySelector("input[name=password]");
        const form = (pw || email) && (pw || email).form;
        const eyeButton = document.querySelector(".o_tai_eye");
        const hasError = Boolean(document.querySelector(".o_tai_login_card .alert-danger"));
        const GREETING = "Hi! I'm Techno AI \u{1F44B} Sign in to continue.";
        const MOUTH = {
            smile: "M53 60 Q60 64 67 60",
            open: "M54 60 Q60 67 66 60 Z",
            flat: "M54 61 L66 61",
            sad: "M53 63 Q60 58 67 63",
        };
        const fieldFocused = () => document.activeElement === email || document.activeElement === pw;
        const say = (text) => {
            if (bubble.textContent === text) {
                return;
            }
            bubble.textContent = text;
            bubble.classList.remove("o_pop");
            void bubble.offsetWidth;
            bubble.classList.add("o_pop");
        };
        const look = (dx, dy) => {
            eyes.style.transform = `translate(${Math.max(-6, Math.min(6, dx))}px, ${Math.max(-4, Math.min(4, dy))}px)`;
        };
        const face = (m) => {
            mouth.setAttribute("d", MOUTH[m]);
            mouth.setAttribute("fill", m === "open" ? "#9fe7e7" : "none");
        };
        const pose = (p) => {
            bot.classList.remove("o_cover", "o_peek");
            if (p) {
                bot.classList.add(p);
            }
        };
        const once = (cls) => {
            bot.classList.remove("o_shake", "o_happy");
            void bot.getBoundingClientRect();
            bot.classList.add(cls);
            setTimeout(() => bot.classList.remove(cls), 650);
        };
        const idle = () => {
            pose(null);
            face("smile");
            say(email && pw && email.value && pw.value ? "Ready? Let's sign in \u{1F680}" : GREETING);
        };

        document.addEventListener("mousemove", (e) => {
            if (fieldFocused()) {
                return;
            }
            const r = bot.getBoundingClientRect();
            look((e.clientX - (r.left + r.width / 2)) / 40, (e.clientY - (r.top + r.height / 2)) / 50);
        });

        if (email) {
            const followText = () => look(-6 + Math.min(email.value.length, 30) * 0.4, 4);
            email.addEventListener("focus", () => {
                pose(null);
                face("open");
                say("What's your work email? ✉️");
                followText();
            });
            email.addEventListener("input", () => {
                followText();
                say(email.value.includes("@") ? "Looks good! \u{1F44D}" : "What's your work email? ✉️");
            });
        }
        if (pw) {
            const onPassword = () => {
                pose(pw.type === "text" ? "o_peek" : "o_cover");
                face("flat");
                say(pw.type === "text" ? "Just a tiny peek… \u{1F440}" : "Your password — I won't look! \u{1F648}");
                look(0, 0);
            };
            pw.addEventListener("focus", onPassword);
            if (eyeButton) {
                // the show-password button switches the field type first, then the robot follows
                eyeButton.addEventListener("click", () => setTimeout(() => {
                    pw.focus();
                    onPassword();
                }, 0));
            }
        }
        [email, pw].filter(Boolean).forEach((el) =>
            el.addEventListener("blur", () => setTimeout(() => {
                if (!fieldFocused()) {
                    idle();
                }
            }, 0))
        );

        const link = document.querySelector(".o_tai_bot_link");
        link.addEventListener("mouseenter", () => {
            if (!fieldFocused()) {
                say("Click me to go home \u{1F3E0}");
            }
        });
        link.addEventListener("mouseleave", () => {
            if (!fieldFocused()) {
                idle();
            }
        });

        if (form) {
            form.addEventListener("submit", () => {
                pose(null);
                face("open");
                say("Welcome back! Signing you in… ✨");
                once("o_happy");
            });
            form.addEventListener("invalid", () => {
                pose(null);
                face("sad");
                say("Hmm, something is missing \u{1F914}");
                once("o_shake");
            }, true);
        }

        if (hasError) {
            face("sad");
            say("That didn't work \u{1F615} Check your email and password.");
            setTimeout(() => once("o_shake"), 300);
        } else if (window.location.pathname === "/web/reset_password") {
            say("No worries, I'll help you reset it \u{1F511}");
        }
    }

    // ---------------------------------------------------------------- 3D background
    const canvas = document.getElementById("o_tai_terrain");
    const ctx = canvas && canvas.getContext("2d");
    if (!ctx) {
        return;
    }
    let w, h, t = 0, mx = 0, my = 0, tx = 0, ty = 0;
    const size = () => {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        w = window.innerWidth;
        h = window.innerHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    size();
    window.addEventListener("resize", size);
    window.addEventListener("mousemove", (e) => {
        tx = e.clientX / w - 0.5;
        ty = e.clientY / h - 0.5;
    });
    const COLS = 70, ROWS = 42, GAP = 46;
    const frame = () => {
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
                ctx.fillStyle = `rgba(${Math.round(40 + 119 * lift)}, ${Math.round(159 + 72 * lift)}, ${Math.round(183 + 48 * lift)}, ${0.08 + near * 0.45})`;
                ctx.beginPath();
                ctx.arc(px, py, Math.max(0.6, 1.8 * s), 0, Math.PI * 2);
                ctx.fill();
            }
        }
        if (!reduce && document.visibilityState === "visible") {
            requestAnimationFrame(frame);
        }
    };
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            requestAnimationFrame(frame);
        }
    });
    frame();
})();
