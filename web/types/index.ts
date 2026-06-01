export type Persona = 'resident' | 'developer' | 'employee';

export interface TownConfig {
  slug: string;
  name: string;
  state: string;
  pineconeIndex: string;
  systemPrompt: string;
}

export interface Citation {
  source: string;
  page: number;
  section: string;
  docType: string;
  excerpt: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
}
