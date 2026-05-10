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
	image_url: string | null;
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

export interface FeedItem {
	type: 'article' | 'group';
	id: number;
	title: string | null;
	summary: string | null;
	category: string;
	importance_score: number;
	tags: Tag[];
	// Article fields
	url?: string | null;
	author?: string | null;
	published_at?: string | null;
	content_type?: string;
	classified_at?: string;
	// Group fields
	grouped_date?: string | null;
	member_count?: number;
}

export interface GroupMemberArticle {
	id: number;
	title: string | null;
	url: string | null;
	author: string | null;
	published_at: string | null;
	summary: string | null;
	importance_score: number;
}

export interface GroupDetail {
	id: number;
	title: string;
	summary: string;
	detail: string;
	category: string;
	grouped_date: string;
	member_count: number;
	created_at: string;
	members: GroupMemberArticle[];
}

export interface FeedResponse {
	items: FeedItem[];
	total: number;
	page: number;
	size: number;
	pages: number;
}

export interface SavedItems {
	articles: number[];
	groups: number[];
}
