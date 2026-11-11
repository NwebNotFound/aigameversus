/** The chronicle tab: which styles and languages the arena tells, and how a failure reads. */

export const STYLES = [
	{ id: 'epic', label: 'Epic' },
	{ id: 'news', label: 'News anchor' },
	{ id: 'sports', label: 'Sports commentator' },
	{ id: 'novel', label: 'Light novel' }
] as const;

export const LANGS = [
	{ id: 'en', label: 'English' },
	{ id: 'de', label: 'Deutsch' }
] as const;

export type StyleId = (typeof STYLES)[number]['id'];
export type LangId = (typeof LANGS)[number]['id'];

export const isStyle = (value: unknown): value is StyleId => STYLES.some((s) => s.id === value);
export const isLang = (value: unknown): value is LangId => LANGS.some((l) => l.id === value);

export interface ChapterText {
	number: number;
	title: string;
	text: string;
}

export interface Chronicle {
	game: string;
	style: string;
	lang: string;
	title: string;
	chapters: ChapterText[];
}

/** The page's own address for a chronicle (it asks the arena); `markdown` is the download. */
export function chroniclePath(
	id: string,
	style: StyleId,
	lang: LangId,
	format: 'json' | 'markdown' = 'json'
): string {
	const query = new URLSearchParams({ style, lang, format });
	return `/replays/${encodeURIComponent(id)}/chronicle?${query}`;
}

/** What to tell the viewer when the chronicle did not come, by the status the server answered. */
export function explain(status: number): string {
	if (status === 409) {
		return 'The match is not over yet. Its chronicle names hidden cards and roles, so it exists once the match has finished.';
	}
	if (status === 404) return 'This game has no chronicle yet.';
	if (status === 502) return 'The arena did not answer. Is the stack running?';
	return `The chronicle could not be loaded (${status}).`;
}
