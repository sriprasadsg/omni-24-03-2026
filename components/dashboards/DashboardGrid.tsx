import React, { useMemo } from 'react';
import { GridLayout, useContainerWidth, type Layout } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import type { CatalogueWidget, Placement } from '../../services/dashboardsApi';
import { WidgetCard } from './WidgetCard';

export const GRID_COLUMNS = 12;
const ROW_HEIGHT = 72;
const GAP = 16;
// Below this width a 12-column grid is too narrow to read: widgets stack in layout order.
const STACK_BELOW = 640;

interface DashboardGridProps {
  widgets: Placement[];
  catalogue: Record<string, CatalogueWidget>;
  editing?: boolean;
  selectedId?: string | null;
  onLayoutChange?: (widgets: Placement[]) => void;
  onRemove?: (i: string) => void;
  onHide?: (i: string) => void;
  onSelect?: (i: string) => void;
  onKeyDown?: (i: string, e: React.KeyboardEvent) => void;
}

/** Reading order: top to bottom, then left to right (what keyboard and stacked views follow). */
export const readingOrder = (widgets: Placement[]) =>
  [...widgets].sort((a, b) => a.y - b.y || a.x - b.x);

export function DashboardGrid({ widgets, catalogue, editing, selectedId, onLayoutChange, onRemove, onHide, onSelect, onKeyDown }: DashboardGridProps) {
  // Measure before the first render: drawing at an assumed width and then switching between grid
  // and stacked layout would jump the page (and remount every widget).
  const { width, containerRef, mounted } = useContainerWidth({ measureBeforeMount: true });
  const layout: Layout = useMemo(() => widgets.map(w => {
    const size = catalogue[w.widget]?.size;
    return { i: w.i, x: w.x, y: w.y, w: w.w, h: w.h,
             minW: size?.minW, minH: size?.minH, maxH: size?.maxH };
  }), [widgets, catalogue]);

  const card = (w: Placement) => (
    <WidgetCard placement={w} spec={catalogue[w.widget]} editing={editing} selected={selectedId === w.i}
                onRemove={onRemove ? () => onRemove(w.i) : undefined}
                onHide={onHide ? () => onHide(w.i) : undefined}
                onSelect={onSelect ? () => onSelect(w.i) : undefined}
                onKeyDown={onKeyDown ? e => onKeyDown(w.i, e) : undefined} />
  );

  const stacked = mounted && width < STACK_BELOW;
  return (
    <div ref={containerRef} className="w-full">
      {stacked ? (
        <div className="space-y-4">
          {readingOrder(widgets).map(w => (
            <div key={w.i} style={{ height: Math.max(160, w.h * ROW_HEIGHT + (w.h - 1) * GAP) }}>{card(w)}</div>
          ))}
        </div>
      ) : mounted ? (
        <GridLayout
          width={width}
          layout={layout}
          gridConfig={{ cols: GRID_COLUMNS, rowHeight: ROW_HEIGHT, margin: [GAP, GAP], containerPadding: [0, 0] }}
          dragConfig={{ enabled: !!editing, handle: '.widget-drag', cancel: '.widget-actions' }}
          resizeConfig={{ enabled: !!editing, handles: ['se'] }}
          className={editing ? 'omni-grid omni-grid-editing' : 'omni-grid'}
          onLayoutChange={next => {
            if (!editing || !onLayoutChange) return;
            const byId = new Map(next.map(item => [item.i, item]));
            const moved = widgets.map(w => {
              const item = byId.get(w.i);
              return item ? { ...w, x: item.x, y: item.y, w: item.w, h: item.h } : w;
            });
            if (moved.some((w, n) => w.x !== widgets[n].x || w.y !== widgets[n].y || w.w !== widgets[n].w || w.h !== widgets[n].h)) {
              onLayoutChange(moved);
            }
          }}
        >
          {widgets.map(w => <div key={w.i}>{card(w)}</div>)}
        </GridLayout>
      ) : null}
    </div>
  );
}
