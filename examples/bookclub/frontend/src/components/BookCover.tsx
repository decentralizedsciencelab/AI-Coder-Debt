import type { Book } from '../types';

const colors = ['#315c53', '#b8513d', '#765a91', '#b98a3c', '#385d7a'];

export default function BookCover({ book, size = 'medium' }: { book: Book; size?: 'small' | 'medium' | 'large' }) {
  const fallbackColor = colors[book.title.charCodeAt(0) % colors.length];
  return book.coverUrl
    ? <img className={`book-cover ${size}`} src={book.coverUrl} alt={`Cover of ${book.title}`} />
    : <div className={`book-cover placeholder ${size}`} style={{ background: fallbackColor }}><b>{book.title}</b><small>{book.author}</small></div>;
}

