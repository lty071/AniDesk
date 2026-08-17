export interface CloudVersion {
  id: string;
  name: string;
  updatedAt: string;
  size: number;
}

export interface CloudSyncProvider {
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  upload(name: string, data: Uint8Array): Promise<CloudVersion>;
  download(versionId: string): Promise<Uint8Array>;
  listVersions(): Promise<CloudVersion[]>;
}

export class CloudSyncNotConfigured implements CloudSyncProvider {
  private unavailable(): never {
    throw new Error("云同步将在第二阶段接入，目前请使用本地备份。");
  }
  async connect(): Promise<void> { this.unavailable(); }
  async disconnect(): Promise<void> { return; }
  async upload(_name: string, _data: Uint8Array): Promise<CloudVersion> { return this.unavailable(); }
  async download(_versionId: string): Promise<Uint8Array> { return this.unavailable(); }
  async listVersions(): Promise<CloudVersion[]> { return this.unavailable(); }
}
