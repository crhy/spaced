# Spaced Linux Visual Polish Implementation Checklist

This checklist converts the first-install screenshot audit into concrete implementation and validation work.

## Non-negotiable visual rules

- [ ] Keep the Calamares partition bars bright and highly differentiated.
- [ ] Keep destructive actions and data-loss warnings visibly colored and unmistakable.
- [ ] Apply the monochrome guideline to decorative UI, navigation, branding, buttons, borders, focus states, window chrome, and noncritical indicators.
- [ ] Preserve the identity of optional nostalgia themes while fixing broken contrast, incorrect states, and inconsistent assets.
- [ ] Do not reduce usability or hide semantic warning/error states merely to achieve monochrome styling.

## Screenshot selections

### Website

- [ ] Use `Screenshot at 2026-07-28 20-30-14.png` as the primary Compiz/visual-effects image.
- [ ] Use `Screenshot at 2026-07-29 00-58-13.png` as the primary real-desktop/features image.
- [ ] Use `Screenshot at 2026-07-28 23-23-48.png` for the first-run experience.
- [ ] Use `Screenshot at 2026-07-29 01-48-41.png` for the applications/Bazaar section.
- [ ] Use a corrected version of `Screenshot at 2026-07-29 04-41-57.png` for the installation section.
- [ ] Use `Screenshot at 2026-07-29 04-44-00.png` for installation documentation or the installer gallery.

### README

- [ ] Replace the old bright desktop screenshot with `Screenshot at 2026-07-29 00-58-13.png`.
- [ ] Add `Screenshot at 2026-07-28 20-30-14.png` to demonstrate Compiz.
- [ ] Add `Screenshot at 2026-07-28 23-23-48.png` to demonstrate first boot.
- [ ] Add the corrected Calamares welcome screenshot after the logo and palette fixes.
- [ ] Use concise alt text describing the actual screen rather than generic “screenshot” text.

### Image preparation

- [ ] Copy selected original PNG files into a tracked source-images directory.
- [ ] Preserve full-resolution PNG originals.
- [ ] Create optimized WebP derivatives for the website.
- [ ] Use predictable semantic names rather than timestamp filenames.
- [ ] Record image source, crop, output dimensions, and intended placement.
- [ ] Avoid screenshots containing YouTube, inbox counts, unrelated browser tabs, save dialogs, or debugging clutter.

## Shared visual specification

- [ ] Define one documented graphite/silver default palette.
- [ ] Define background, surface, raised surface, border, primary text, secondary text, hover, active, selected, disabled, and focus colors.
- [ ] Define separate semantic warning, error, success, and destructive-action colors.
- [ ] Define spacing, icon padding, titlebar height, corner radius, border width, and focus-ring rules.
- [ ] Use shared source values where practical instead of duplicating slightly different colors throughout components.
- [ ] Document the palette and state matrix in the repository.

## Calamares branding and theme

Related issues: #36 and #41.

### Logo

- [ ] Identify the exact Calamares logo asset currently used.
- [ ] Replace it with a tightly cropped PNG or SVG with genuine transparency.
- [ ] Remove the baked square/matte background.
- [ ] Verify the logo on dark, medium-gray, and light test backgrounds.
- [ ] Ensure the sidebar icon and large welcome logo use the same approved artwork.
- [ ] Verify sharp rendering at normal DPI and HiDPI.

### Window and navigation

- [ ] Replace blue/default navigation selection with the approved graphite/silver state.
- [ ] Fix navigation hover, selected, disabled, and focus states.
- [ ] Fix button normal, hover, active, focused, disabled, and destructive states.
- [ ] Fix text alignment and vertical centering in navigation and buttons.
- [ ] Normalize panel borders, separators, group boxes, and input outlines.
- [ ] Ensure page headings and body text follow one hierarchy.

### Installer content

- [ ] Keep partition bars and disk-operation warning colors bright and unchanged.
- [ ] Keep erase-disk warnings visibly red or amber.
- [ ] Retheme only surrounding partition-page chrome and controls.
- [ ] Replace outdated slideshow screenshots with current dark Spaced screenshots.
- [ ] Make slideshow typography and captions match current branding.
- [ ] Remove outdated blue/green decorative accents that are not semantic.
- [ ] Verify Calamares at 1280x720, 1920x1080, and 2x scaling.
- [ ] Capture corrected welcome, location, partition, summary, and installation-progress screenshots.

## Default dark theme state audit

Related issue: #36.

- [ ] Audit GTK 2 normal, hover, active, selected, disabled, focus, warning, and error states.
- [ ] Audit GTK 3 normal, hover, active, selected, disabled, focus, warning, and error states.
- [ ] Audit GTK 4/libadwaita-compatible applications where overrides are technically supported.
- [ ] Audit titlebars, tabs, menus, context menus, toolbars, scrollbars, switches, sliders, progress bars, and separators.
- [ ] Fix buttons that use unintended blue, green, orange, or white states.
- [ ] Fix labels that appear visually off-center because their surrounding colors or borders are inconsistent.
- [ ] Fix low-contrast disabled text and controls.
- [ ] Fix mismatched focus rings and selection backgrounds.
- [ ] Verify dialogs such as Save Screenshot, file chooser, authentication, and warning dialogs.
- [ ] Verify Control Center pages and category buttons.
- [ ] Verify the first-run Welcome application.
- [ ] Preserve accessibility and keyboard-focus visibility.

## Application integration

Related issues: #10 and #45.

- [ ] Make Volume Control follow the selected dark theme.
- [ ] Make LibreOffice follow the selected theme as far as supported.
- [ ] Verify Brave Flatpak portals, file choosers, titlebar integration, and dark preference.
- [ ] Determine whether Bazaar can follow the dark preference without unsupported hacks.
- [ ] Where an app cannot be fully themed, ensure its surrounding integration still looks intentional.
- [ ] Verify representative GTK, Qt, Electron, and Flatpak applications.
- [ ] Verify theme behavior after logout, reboot, and a new user account.
- [ ] Verify keyring, portal, notification, and default-application integration.

## First-run Welcome application

- [ ] Replace orange/non-brand decorative accents with graphite/silver equivalents.
- [ ] Preserve obvious hover, focus, and clickable states.
- [ ] Normalize card backgrounds, borders, spacing, and arrow alignment.
- [ ] Use consistent high-resolution icons.
- [ ] Verify keyboard navigation.
- [ ] Verify normal DPI and HiDPI.
- [ ] Capture the corrected first-run screenshot for the website.

## Icons

Related issues: #6, #37, and #38.

- [ ] Inventory every desktop, panel, menu, application, action, device, status, MIME, notification, and Control Center icon.
- [ ] Replace pixelated raster assets with SVG or complete multi-resolution sets.
- [ ] Normalize transparent padding so icons appear optically centered.
- [ ] Provide correct 16, 22, 24, 32, 48, 64, 96, 128, and scalable assets where required.
- [ ] Fix Computer, Home, Installer, Trash, and mounted-drive desktop icons.
- [ ] Fix the low-resolution `data`/external-drive icon.
- [ ] Fix Control Center icon-family inconsistencies.
- [ ] Fix panel and notification-area icons that use inappropriate fallbacks.
- [ ] Verify icon-theme inheritance.
- [ ] Rebuild icon caches during ISO construction.
- [ ] Test 1x, 1.5x, and 2x scale factors.

## Panel and audio presentation

- [ ] Restore the volume icon in the notification area by default.
- [ ] Verify its icon states for muted, low, medium, and high volume.
- [ ] Verify the icon remains sharp at all supported panel sizes.
- [ ] Verify network, clock, home/session, notification, and volume icons have consistent sizing.
- [ ] Verify vertical alignment and spacing of every panel applet.
- [ ] Verify panel layout persistence after reboot and new-user creation.

## Compiz visual presentation

- [ ] Replace the saturated default blue cube environment with a restrained dark navy/graphite background.
- [ ] Preserve enough contrast to distinguish the cube edges.
- [ ] Verify reflections, opacity, cube caps, and deformation effects with the dark wallpaper.
- [ ] Verify optional bright themes still remain legible against the cube environment.
- [ ] Confirm this visual change does not alter renderer selection or the NVIDIA/NVK workaround.
- [ ] Capture a new Compiz cube screenshot after the background correction.

## Website and README implementation

- [ ] Add semantic screenshot filenames under the existing website asset structure.
- [ ] Replace outdated website screenshots.
- [ ] Replace outdated README screenshots.
- [ ] Keep screenshot dimensions and aspect ratios consistent within galleries.
- [ ] Add meaningful alt text and captions.
- [ ] Optimize WebP output without visible text degradation.
- [ ] Verify mobile, tablet, and desktop layouts.
- [ ] Verify no screenshot is stretched or upscaled beyond its source resolution.
- [ ] Verify links and image paths work on GitHub and Cloudflare Pages.

## Validation matrix

- [ ] Capture before/after screenshots for every changed component.
- [ ] Test the default dark theme at normal DPI and HiDPI.
- [ ] Test every shipped optional theme for regressions.
- [ ] Test fresh live boot, installed first boot, and a new user account.
- [ ] Test Calamares from welcome through installation completion.
- [ ] Test the panel, Control Center, Volume Control, Welcome app, Bazaar, Brave, and common dialogs.
- [ ] Run desktop-file, shell, Python, icon-cache, and repository whitespace validation.
- [ ] Record visual review results in the relevant GitHub issue.
- [ ] Do not close an issue solely because code was committed; required visual or hardware validation must also pass.

## Issue closure rules

- [ ] Close #36 only after every shipped theme completes the state/color screenshot audit.
- [ ] Close #37 only after common icons are sharp at normal DPI and HiDPI.
- [ ] Close #38 only after mounted-drive icons are sharp in Caja, desktop, and dialogs.
- [ ] Close #41 only after Calamares, boot, login, and desktop branding use approved assets and palette.
- [ ] Close #10 only after representative bundled applications follow the chosen theme or have documented technical limitations.
- [ ] Close #45 only after representative Flatpaks pass portal, keyring, default-app, and theming tests.
- [ ] Close #6 only after titlebar controls and icons pass HiDPI testing.
- [ ] Close the screenshot-refresh issue only after website and README changes are published and verified.
