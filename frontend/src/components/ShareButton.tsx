import { shareUrl, type UrlState } from "../lib/urlState";

export function ShareButton({ state }: { state: UrlState }) {
  return (
    <button
      type="button"
      onClick={async () => {
        const url = shareUrl(state);
        await navigator.clipboard.writeText(url);
        alert("Link copied. Embed with ?embed=1");
      }}
    >
      Copy share link
    </button>
  );
}
