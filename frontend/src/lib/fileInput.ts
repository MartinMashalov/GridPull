/**
 * Safe attribute overrides for hidden file inputs.
 *
 * macOS NSOpenPanel (the native file picker invoked by <input type="file">)
 * inspects the input element's accessible name (label text, `aria-label`,
 * `name`, `id`, surrounding label text) and the document title to seed its
 * saved-search state. When those values contain product/workflow words like
 * "GridPull" or "new_submission", the picker can open with the search field
 * pre-populated and a saved-search scope active, hiding the user's actual
 * folder contents.
 *
 * To prevent that leakage, we always pass a neutral, generic accessible
 * name and an empty `name` to every hidden file input — both react-dropzone
 * inputs (via `getInputProps(SAFE_FILE_INPUT_PROPS)`) and any raw
 * `<input type="file">` elements rendered directly. The values below are
 * deliberately generic ("Upload file") so the OS picker has nothing
 * product-specific to retain in its search state.
 */
export const SAFE_FILE_INPUT_PROPS = {
  name: '',
  id: '',
  'aria-label': 'Upload file',
  title: 'Upload file',
} as const
