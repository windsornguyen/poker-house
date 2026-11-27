# Third-party notices

The third-party packages the built client contains, with their licences and
the paths of their licence texts, relative to `apps/web/`. `pnpm
build` copies each licence text into `dist/THIRD_PARTY_NOTICES.txt`.

The dockview packages publish no licence file, so `dockview/LICENSE.md` holds
the licence from the dockview source at the pinned version, verbatim.
The scheduler licence is copied verbatim from the pinned package so the build
does not depend on a package manager hoisting transitive dependencies.

| Package       | Version | Licence | Licence text                   |
| ------------- | ------- | ------- | ------------------------------ |
| dockview      | 4.13.1  | MIT     | licenses/dockview/LICENSE.md   |
| dockview-core | 4.13.1  | MIT     | licenses/dockview/LICENSE.md   |
| react         | 19.3.1  | MIT     | node_modules/react/LICENSE     |
| react-dom     | 19.3.1  | MIT     | node_modules/react-dom/LICENSE |
| scheduler     | 0.28.0  | MIT     | licenses/scheduler/LICENSE.md  |
