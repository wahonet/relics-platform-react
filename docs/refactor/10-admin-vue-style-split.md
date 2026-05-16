# Step 10 - Admin Vue Style Split

Date: 2026-05-16

## What Changed

- Extracted scoped styles from `platform/admin-vue/src/components/RelicEditDialog.vue` to `platform/admin-vue/src/styles/relic-edit-dialog.css`.
- Extracted global Element Plus dialog overrides from `RelicEditDialog.vue` to `platform/admin-vue/src/styles/relic-edit-dialog-global.css`.
- Extracted scoped styles from `platform/admin-vue/src/views/Relics.vue` to `platform/admin-vue/src/styles/relics.css`.
- Kept component templates, props, emitted events and business logic unchanged.

## Verification

- `npm.cmd run typecheck` in `platform/admin-vue` passed after the split.

## Next Step

- Prefer future feature work to create composables or child components for dialog subdomains such as mini map, audit history and neighbor query.
