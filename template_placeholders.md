# Description Template Placeholders

Available for use in description auto-fill templates. Enclose a placeholder in curly braces, for example:

```text
{artist} - {title}
```

- [Album-Level Placeholders](#album-level-placeholders)
- [Track-Level Placeholders](#track-level-placeholders)
- [Examples](#examples)
- [Notes](#notes)

---

## Album-Level Placeholders

These placeholders work in all template modes.

| Placeholder          | Description                                                              |
| :------------------- | :----------------------------------------------------------------------- |
| `{album}`            | Album name                                                               |
| `{artist}`           | Album artist                                                             |
| `{date}`             | Release / publish date                                                   |
| `{tags}`             | Album tags / genres                                                      |
| `{tracks}`           | Number of tracks                                                         |
| `{tracklist}`        | Full formatted tracklist (all tracks)                                    |
| `{album_info}`       | Album info section (album, artist, date, tags, tracks)                   |
| `{track_comments}`   | Track comments section                                                   |
| `{technical_details}`| Technical details section (format, bitrate, size per track)              |

---

## Track-Level Placeholders

In per-track template modes, these are applied to each track individually. In album modes that also contain album-level placeholders, the first track's values are used.

| Placeholder       | Description                                                          |
| :---------------- | :------------------------------------------------------------------- |
| `{n}`             | Track number (1-based index)                                         |
| `{track_no}`      | Raw track number from file metadata (may differ from `{n}`)          |
| `{artist}`        | Track artist                                                         |
| `{title}`         | Track title                                                          |
| `{comment}`       | Track comment / description                                          |
| `{length}`        | Track duration (e.g. `3:45`)                                        |
| `{format}`        | File extension (e.g. `.mp3`, `.flac`)                                |
| `{bitrate}`       | Audio bitrate (e.g. `256 kbps`)                                      |
| `{size}`          | File size (e.g. `7.9 MB`)                                            |
| `{price}`         | Track price (e.g. `$0`)                                              |
| `{nyp}`           | Name Your Price (`Yes` / `No`)                                       |
| `{year}`          | Year from metadata                                                   |
| `{genre}`         | Genre from metadata                                                  |
| `{sample_rate}`   | Sample rate (e.g. `44100 Hz`)                                        |
| `{channels}`      | Number of audio channels                                             |
| `{bit_depth}`     | Bit depth (e.g. `16`, `24`)                                          |
| `{filename}`      | Track filename without extension or path                             |
| `{track_album}`   | Album name from track metadata                                       |
| `{track_artist}`  | Track artist (same as `{artist}`)                                    |
| `{album_artist}`  | Album artist from track metadata                                     |
| `{composer}`      | Composer from metadata                                               |
| `{isrc}`          | ISRC code from metadata                                              |

---

## Examples

<details>
<summary><b>Minimal album description</b></summary>

```text
{album} by {artist}
Released {date}

{tracklist}
```

</details>

<details>
<summary><b>Per-track line</b></summary>

```text
{n}. {artist} - {title} ({length})
```

</details>

<details>
<summary><b>Full technical sheet</b></summary>

```text
{album_info}

{technical_details}
```

</details>

---

## Notes

> [!NOTE]
> `{artist}` resolves to the album artist in album-level templates and to the track artist in per-track templates. Use `{album_artist}` if you always need the album-level value.

> [!TIP]
> Combine `{tracklist}` with `{track_comments}` to render a full tracklist followed by per-track notes in a single template.

> [!IMPORTANT]
> Placeholder names are case-sensitive. `{Artist}` will not be substituted.

> [!WARNING]
> Unknown placeholders are left in the output verbatim. Double-check your template for typos before uploading.

> [!CAUTION]
> In album-level modes, every track-level placeholder uses the **first track's** metadata. If you need per-track values, switch to a per-track template mode.
