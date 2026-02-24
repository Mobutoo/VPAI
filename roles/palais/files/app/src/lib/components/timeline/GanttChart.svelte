<script lang="ts">
	import { scaleTime } from 'd3-scale';
	import { timeDay, timeWeek, timeMonth } from 'd3-time';

	type Task = {
		id: number;
		title: string;
		startDate: Date | string | null;
		endDate: Date | string | null;
	};

	type Dependency = {
		taskId: number;
		dependsOnTaskId: number;
		dependencyType: string;
	};

	let {
		tasks,
		dependencies,
		criticalPathIds,
		projectId
	}: {
		tasks: Task[];
		dependencies: Dependency[];
		criticalPathIds: number[];
		projectId: number;
	} = $props();

	// Layout constants
	const ROW_H = 36;
	const LABEL_W = 200;
	const HEADER_H = 40;
	const ARROW_R = 4;
	const MIN_BAR_W = 6;

	// Zoom levels
	const ZOOM_LEVELS = ['day', 'week', 'month'] as const;
	type ZoomLevel = (typeof ZOOM_LEVELS)[number];
	let zoom = $state<ZoomLevel>('week');

	// Normalize dates
	const normTasks = $derived(tasks.map((t) => ({
		...t,
		start: t.startDate ? new Date(t.startDate) : null,
		end: t.endDate ? new Date(t.endDate) : null
	})));

	// Compute time domain
	const domain = $derived(() => {
		const dated = normTasks.filter((t) => t.start && t.end);
		if (dated.length === 0) {
			const now = new Date();
			return [now, new Date(now.getTime() + 30 * 86_400_000)] as [Date, Date];
		}
		const minDate = new Date(Math.min(...dated.map((t) => t.start!.getTime())));
		const maxDate = new Date(Math.max(...dated.map((t) => t.end!.getTime())));
		// Pad by 1 unit on each side
		minDate.setDate(minDate.getDate() - 1);
		maxDate.setDate(maxDate.getDate() + 1);
		return [minDate, maxDate] as [Date, Date];
	});

	// Chart width (pixels for time axis)
	const CHART_W = $derived(() => {
		const [start, end] = domain();
		const days = (end.getTime() - start.getTime()) / 86_400_000;
		if (zoom === 'day') return Math.max(600, days * 40);
		if (zoom === 'week') return Math.max(600, days * 12);
		return Math.max(600, days * 4);
	});

	// d3 scale
	const xScale = $derived(() => {
		return scaleTime().domain(domain()).range([0, CHART_W()]);
	});

	// Tick config per zoom
	const ticks = $derived(() => {
		const scale = xScale();
		const [start, end] = domain();
		if (zoom === 'day') return timeDay.range(start, end);
		if (zoom === 'week') return timeWeek.range(start, end);
		return timeMonth.range(start, end);
	});

	function tickLabel(d: Date): string {
		if (zoom === 'day') return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
		if (zoom === 'week') return `S${getWeek(d)} ${d.toLocaleDateString('fr-FR', { month: 'short' })}`;
		return d.toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' });
	}

	function getWeek(d: Date): number {
		const start = new Date(d.getFullYear(), 0, 1);
		return Math.ceil(((d.getTime() - start.getTime()) / 86400000 + start.getDay() + 1) / 7);
	}

	// Critical path set
	const cpSet = $derived(new Set(criticalPathIds));

	// Bar rect per task
	type Bar = {
		id: number;
		title: string;
		x: number;
		w: number;
		y: number;
		isCritical: boolean;
		hasDate: boolean;
	};

	const bars = $derived((): Bar[] => {
		const scale = xScale();
		const cw = CHART_W();
		return normTasks.map((t, i) => {
			const isCritical = cpSet.has(t.id);
			if (t.start && t.end) {
				const x = scale(t.start);
				const w = Math.max(MIN_BAR_W, scale(t.end) - x);
				return { id: t.id, title: t.title, x, w, y: HEADER_H + i * ROW_H, isCritical, hasDate: true };
			}
			// Placeholder at right edge for undated tasks
			return { id: t.id, title: t.title, x: cw - 40, w: 40, y: HEADER_H + i * ROW_H, isCritical, hasDate: false };
		});
	});

	// Arrow paths for dependencies
	type Arrow = { d: string };
	const arrows = $derived((): Arrow[] => {
		const barMap = new Map(bars().map((b) => [b.id, b]));
		return dependencies.flatMap((dep): Arrow[] => {
			const from = barMap.get(dep.dependsOnTaskId);
			const to = barMap.get(dep.taskId);
			if (!from || !to) return [];
			// Arrow from end of "from" bar to start of "to" bar
			const x1 = from.x + from.w;
			const y1 = from.y + ROW_H / 2;
			const x2 = to.x;
			const y2 = to.y + ROW_H / 2;
			const cx = (x1 + x2) / 2;
			return [{
				d: `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`
			}];
		});
	});

	// Drag state
	let dragging = $state<{
		taskId: number;
		mode: 'move' | 'resize-end';
		startX: number;
		origStart: Date | null;
		origEnd: Date | null;
	} | null>(null);

	let svgEl: SVGSVGElement | undefined;
	let saving = $state(false);

	function getSvgX(e: MouseEvent): number {
		if (!svgEl) return 0;
		const rect = svgEl.getBoundingClientRect();
		return e.clientX - rect.left - LABEL_W;
	}

	function onBarMousedown(e: MouseEvent, taskId: number, mode: 'move' | 'resize-end') {
		e.preventDefault();
		const t = normTasks.find((t) => t.id === taskId);
		if (!t) return;
		dragging = { taskId, mode, startX: getSvgX(e), origStart: t.start, origEnd: t.end };
	}

	function onMousemove(e: MouseEvent) {
		if (!dragging) return;
		const scale = xScale();
		const dx = getSvgX(e) - dragging.startX;
		const dMs = scale.invert(scale(new Date(0)) + dx).getTime() - new Date(0).getTime();
		const t = normTasks.find((t) => t.id === dragging!.taskId);
		if (!t) return;
		if (dragging.mode === 'move' && dragging.origStart && dragging.origEnd) {
			t.start = new Date(dragging.origStart.getTime() + dMs);
			t.end = new Date(dragging.origEnd.getTime() + dMs);
		} else if (dragging.mode === 'resize-end' && dragging.origEnd) {
			t.end = new Date(dragging.origEnd.getTime() + dMs);
		}
	}

	async function onMouseup() {
		if (!dragging) return;
		const d = dragging;
		dragging = null;
		const t = normTasks.find((t) => t.id === d.taskId);
		if (!t || !t.start || !t.end) return;
		saving = true;
		await fetch(`/api/v1/tasks/${d.taskId}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ startDate: t.start.toISOString(), endDate: t.end.toISOString() })
		});
		saving = false;
	}

	const totalH = $derived(HEADER_H + normTasks.length * ROW_H);
</script>

<div class="gantt-wrapper" style="overflow-x: auto; overflow-y: visible;">
	<!-- Zoom controls -->
	<div class="flex items-center gap-2 mb-3">
		{#each ZOOM_LEVELS as z}
			<button
				onclick={() => zoom = z}
				class="px-2.5 py-1 rounded text-xs font-medium transition-all"
				style="
					background: {zoom === z ? 'var(--palais-gold)' : 'var(--palais-surface)'};
					color: {zoom === z ? '#0A0A0F' : 'var(--palais-text-muted)'};
					border: 1px solid {zoom === z ? 'var(--palais-gold)' : 'var(--palais-border)'};
				">
				{z.charAt(0).toUpperCase() + z.slice(1)}
			</button>
		{/each}
		{#if saving}
			<span class="text-xs ml-auto" style="color: var(--palais-cyan);">Saving...</span>
		{/if}
	</div>

	<div class="flex" style="min-width: {LABEL_W + CHART_W()}px;">
		<!-- Labels column -->
		<div class="flex-shrink-0" style="width: {LABEL_W}px; padding-top: {HEADER_H}px;">
			{#each normTasks as task, i}
				<div
					class="flex items-center text-xs truncate pr-2"
					style="
						height: {ROW_H}px;
						color: {cpSet.has(task.id) ? 'var(--palais-red)' : 'var(--palais-text)'};
						border-bottom: 1px solid var(--palais-border);
					">
					{#if cpSet.has(task.id)}<span class="mr-1" title="Critical path">◈</span>{/if}
					<span class="truncate">{task.title}</span>
				</div>
			{/each}
		</div>

		<!-- SVG chart -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<svg
			bind:this={svgEl}
			width={CHART_W()}
			height={totalH}
			onmousemove={onMousemove}
			onmouseup={onMouseup}
			onmouseleave={onMouseup}
			style="cursor: {dragging ? 'grabbing' : 'default'}; flex-shrink: 0;"
		>
			<!-- Background grid -->
			{#each ticks() as tick}
				<line
					x1={xScale()(tick)}
					y1={HEADER_H}
					x2={xScale()(tick)}
					y2={totalH}
					stroke="var(--palais-border)"
					stroke-width="1"
				/>
			{/each}

			<!-- Row backgrounds -->
			{#each normTasks as _, i}
				<rect
					x={0}
					y={HEADER_H + i * ROW_H}
					width={CHART_W()}
					height={ROW_H}
					fill={i % 2 === 0 ? 'var(--palais-surface)' : 'var(--palais-bg)'}
					opacity="0.5"
				/>
			{/each}

			<!-- Time axis header -->
			<rect x={0} y={0} width={CHART_W()} height={HEADER_H}
				fill="var(--palais-surface)" />
			<line x1={0} y1={HEADER_H} x2={CHART_W()} y2={HEADER_H}
				stroke="var(--palais-gold)" stroke-width="1.5" />
			{#each ticks() as tick}
				<text
					x={xScale()(tick) + 4}
					y={HEADER_H - 8}
					font-size="10"
					fill="var(--palais-text-muted)"
					font-family="'JetBrains Mono', monospace"
				>{tickLabel(tick)}</text>
			{/each}

			<!-- Dependency arrows -->
			{#each arrows() as arrow}
				<path
					d={arrow.d}
					fill="none"
					stroke="var(--palais-cyan)"
					stroke-width="1.5"
					stroke-dasharray="4 2"
					opacity="0.7"
				/>
			{/each}

			<!-- Task bars -->
			{#each bars() as bar}
				{@const barColor = bar.isCritical ? 'var(--palais-red)' : 'var(--palais-gold)'}
				{@const barY = bar.y + 6}
				{@const barH = ROW_H - 12}
				<!-- Move handle (whole bar) -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<rect
					x={bar.x}
					y={barY}
					width={bar.w}
					height={barH}
					rx={3}
					fill={barColor}
					opacity={bar.hasDate ? '0.85' : '0.3'}
					cursor="grab"
					onmousedown={(e) => onBarMousedown(e, bar.id, 'move')}
				/>
				<!-- Resize handle (right edge) -->
				{#if bar.hasDate}
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<rect
						x={bar.x + bar.w - 6}
						y={barY}
						width={6}
						height={barH}
						rx={2}
						fill={bar.isCritical ? 'var(--palais-amber)' : 'color-mix(in srgb, var(--palais-gold) 60%, white)'}
						cursor="ew-resize"
						onmousedown={(e) => onBarMousedown(e, bar.id, 'resize-end')}
					/>
				{/if}
			{/each}

			<!-- Today marker -->
			{#if xScale()(new Date()) >= 0 && xScale()(new Date()) <= CHART_W()}
				<line
					x1={xScale()(new Date())}
					y1={HEADER_H}
					x2={xScale()(new Date())}
					y2={totalH}
					stroke="var(--palais-cyan)"
					stroke-width="1.5"
					stroke-dasharray="6 3"
				/>
				<text
					x={xScale()(new Date()) + 3}
					y={HEADER_H + 12}
					font-size="9"
					fill="var(--palais-cyan)"
					font-family="'JetBrains Mono', monospace"
				>TODAY</text>
			{/if}
		</svg>
	</div>

	<!-- Legend -->
	<div class="flex items-center gap-4 mt-3 text-xs" style="color: var(--palais-text-muted);">
		<div class="flex items-center gap-1.5">
			<div class="w-4 h-3 rounded" style="background: var(--palais-gold);"></div>
			<span>Task</span>
		</div>
		<div class="flex items-center gap-1.5">
			<div class="w-4 h-3 rounded" style="background: var(--palais-red);"></div>
			<span>Critical path</span>
		</div>
		<div class="flex items-center gap-1.5">
			<div class="w-4 border-t-2" style="border-color: var(--palais-cyan); border-style: dashed;"></div>
			<span>Dependency</span>
		</div>
		<div class="flex items-center gap-1.5">
			<div class="w-px h-4" style="background: var(--palais-cyan);"></div>
			<span>Today</span>
		</div>
	</div>
</div>
