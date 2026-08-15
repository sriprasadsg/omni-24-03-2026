import { UserRepository, UserService } from './sample_typescript.ts';

describe('UserService', () => {
  it('should create a user', () => {
    const service = new UserService(new UserRepository());
    service.createUser('test', 'test@test.com');
  });

  it('should find a user by id', () => {
    const service = new UserService(new UserRepository());
    const userCreated = service.createUser('test', 'test@test.com');
    const user = service.getUser(userCreated.id);
  });

  test('alternative test syntax', () => {
    new UserService(new UserRepository());
  });
});
