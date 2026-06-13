import { useEffect, useRef, useState } from "react";

// ! I got tired of the chunked response
// * Yes I know this is from network hiccups. To provide the best UX, we want to smooth the text rendering as much as possible

// Reveal ~1/N of the remaining buffer each tick, so it eases out as it catches up
const REVEAL_DIVISOR = 6;
// Always reveal at least this many chars per tick so the tail never stalls
const MIN_STEP = 2;
// Throttle reveals (ms) to bound markdown re-parses while still reading as smooth
const TICK_MS = 30;

/**
 * Smoothly reveal `target` a little at a time, decoupling rendering from the lumpy arrival of streamed network chunks so text flows like typing instead of appearing in bursts
 * Snaps instantly when `target` shrinks or diverges (a new message resets the stream)
 */
export function useSmoothText(target: string): string {
	const [displayed, setDisplayed] = useState(target);
	const targetRef = useRef(target);
	const displayedRef = useRef(target);

	// Keep the latest target readable inside the rAF loop without re-subscribing
	useEffect(() => {
		targetRef.current = target;
	}, [target]);

	useEffect(() => {
		let raf = 0;
		let last = 0;
		const tick = (now: number): void => {
			const tgt = targetRef.current;
			const cur = displayedRef.current;
			if (cur !== tgt) {
				const isReset = cur.length > tgt.length || !tgt.startsWith(cur);
				if (isReset) {
					displayedRef.current = tgt;
					setDisplayed(tgt);
				} else if (now - last >= TICK_MS) {
					last = now;
					const step = Math.max(MIN_STEP, Math.ceil((tgt.length - cur.length) / REVEAL_DIVISOR));
					const next = tgt.slice(0, cur.length + step);
					displayedRef.current = next;
					setDisplayed(next);
				}
			}
			raf = requestAnimationFrame(tick);
		};
		raf = requestAnimationFrame(tick);
		return () => {
			cancelAnimationFrame(raf);
		};
	}, []);

	return displayed;
}
