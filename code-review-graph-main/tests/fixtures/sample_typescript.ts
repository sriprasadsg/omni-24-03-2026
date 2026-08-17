import { Request, Response } from 'express';

interface UserData {
  id: number;
  name: string;
  email: string;
}

export class UserRepository {
  private users: Map<number, UserData> = new Map();

  findById(id: number): UserData | undefined {
    return this.users.get(id);
  }

  save(user: UserData): void {
    this.users.set(user.id, user);
  }
}

export class UserService { constructor(private repo: UserRepository) {}
  getUser(id: number): UserData | undefined {
    return this.repo.findById(id);
  }

  createUser(name: string, email: string): UserData {
    const user: UserData = { id: Date.now(), name, email };
    this.repo.save(user);
    return user;
  }
}

export function handleGetUser(req: Request, res: Response): void {
  const repo = new UserRepository();
  const service = new UserService(repo);
  const user = service.getUser(Number(req.params.id));
  if (user) {
    res.json(user);
  } else {
    res.status(404).json({ error: 'Not found' });
  }
}
