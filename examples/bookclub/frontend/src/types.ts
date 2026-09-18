export interface User {
  id: string;
  name: string;
  email: string;
  createdAt?: string;
}

export interface Book {
  id: string;
  isbn?: string | null;
  title: string;
  author: string;
  description?: string;
  coverUrl?: string | null;
}

export interface Club {
  id: string;
  name: string;
  description: string;
  isPublic: boolean;
  ownerName: string;
  memberCount: number;
  isMember: boolean;
  myRole?: 'owner' | 'moderator' | 'member' | null;
  currentBook?: Book | null;
  createdAt: string;
}

export interface Candidate {
  id: string;
  pitch: string;
  book: Book;
  proposedBy: string;
  voteCount: number;
}

export interface VotingRound {
  id: string;
  title: string;
  closesAt: string;
  closedAt?: string | null;
  status: 'open' | 'closed';
  winnerBookId?: string | null;
  candidates: Candidate[];
  myVote?: string | null;
}

export interface ThreadSummary {
  id: string;
  title: string;
  chapterNumber: number;
  createdAt: string;
  createdBy: string;
  postCount: number;
  lastActivityAt?: string | null;
  book: Book;
}

export interface Post {
  id: string;
  body: string;
  createdAt: string;
  updatedAt: string;
  author: Pick<User, 'id' | 'name'>;
}

export interface ThreadDetail extends Omit<ThreadSummary, 'postCount' | 'lastActivityAt'> {
  clubId: string;
  posts: Post[];
}

