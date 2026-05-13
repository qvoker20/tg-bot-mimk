# CSS Structure

## Shared
- `shared/core.css`: base variables, typography, forms, global utility.
- `shared/layout.css`: shared layout shells and panels.
- `shared/components/buttons.css`: global button styles.
- `shared/components/modals.css`: global modal wrappers.
- `shared/components/alerts.css`: alerts and toast messages.
- `shared/components/loaders.css`: global loading overlay and spinner.
- `shared/components.css`: shared components entrypoint (`@import` only).
- `shared/style.css`: main global entrypoint.

## Assemblers
- `assemblers/data/tables.css`: data/buffer tables and sticky columns.
- `assemblers/data/buttons.css`: data/buffer action buttons.
- `assemblers/data/modals.css`: transfer/main-order/info modals.
- `assemblers/data/layout.css`: screen/page layout and filter rows.
- `assemblers/data/status.css`: status badges.
- `assemblers/data/context-menu.css`: row context menu.
- `assemblers/data.css`: data module entrypoint (`@import` only).

- `assemblers/schedule/toolbar.css`: schedule toolbar and week controls.
- `assemblers/schedule/tables.css`: schedule board/search/edit tables.
- `assemblers/schedule/buttons.css`: schedule-specific action buttons.
- `assemblers/schedule/modals.css`: schedule task modal and modal controls.
- `assemblers/schedule.css`: schedule module entrypoint (`@import` only).
