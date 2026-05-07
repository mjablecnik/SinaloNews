export interface Tag {
	category: string;
	subcategory: string;
}

export interface ArticleSummary {
	id: number;
	title: string | null;
	url: string | null;
	author: string | null;
	published_at: string | null;
	tags: Tag[];
	content_type: string;
	importance_score: number;
	summary: string | null;
	classified_at: string;
}

export interface ArticleDetail extends ArticleSummary {
	extracted_text: string | null;
	formatted_text: string | null;
}

export interface PaginatedResponse {
	items: ArticleSummary[];
	total: number;
	page: number;
	size: number;
	pages: number;
}

export interface CategoryCount {
	category: string;
	count: number;
}

export interface Settings {
	minScore: number;
	daysBack: number;
}

export interface ReadState {
	readArticleIds: number[];
}
