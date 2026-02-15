# Advanced Overrides (`overrides.qss`)

Use `overrides.qss` only when token changes are not enough.

## Best Practices
- Prefer token updates first.
- Scope rules using existing object names.
- Keep overrides minimal and documented with short comments.
- Test all main panels after every override change.

## Avoid
- Broad global selectors like `QWidget { ... }` unless absolutely required.
- Hardcoded colors that conflict with token palette.
- Deep selector chains that are fragile to UI refactors.

## Useful Object Names in Current UI
- `#Sidebar`
- `#SidebarBrand`
- `#StatusStrip`
- `#AlbumCard`
- `#AlbumCover`
- `#AlbumTitle`
- `#TrackRow`
- `#TrackNumber`
- `#TrackTitle`
- `#StatusMuted`

## Example Override
```qss
/* Make album card border slightly stronger on hover */
#AlbumCard:hover {
    border-width: 2px;
}

/* Increase muted status text readability slightly */
#StatusMuted {
    font-size: 9pt;
}
```

## Safety Note
Large or aggressive overrides can reduce compatibility with future app updates. Keep your overrides targeted and resilient.
