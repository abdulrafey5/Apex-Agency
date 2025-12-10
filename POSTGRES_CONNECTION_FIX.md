# Fixing PostgreSQL Connection Error

## Error Message
```
FATAL: no pg_hba.conf entry for host "172.18.203.149", user "postgres", database "inception"
```

## What This Means
The PostgreSQL server at `172.18.203.149` is rejecting your connection because:
1. The `pg_hba.conf` file doesn't have an entry allowing connections from your client IP
2. The server may require SSL, or may not allow SSL connections

## Solutions

### Option 1: Configure PostgreSQL Server (Recommended)

**On the PostgreSQL server** (`172.18.203.149`), edit `/etc/postgresql/*/main/pg_hba.conf`:

```bash
# Find your PostgreSQL config directory
sudo find /etc -name pg_hba.conf

# Edit the file
sudo nano /etc/postgresql/18/main/pg_hba.conf  # Adjust version number
```

**Add this line** to allow connections from your WSL network:
```
# Allow connections from WSL/Windows network
host    inception    postgres    172.18.0.0/16    md5
# Or allow from any IP (less secure, for development only):
host    inception    postgres    0.0.0.0/0         md5
```

**Then restart PostgreSQL:**
```bash
sudo systemctl restart postgresql
```

### Option 2: Use SSL Mode Configuration

If you can't modify the server, try different SSL modes in your `.env`:

```env
# Try these one at a time:
DB_SSLMODE=disable    # No SSL (if server doesn't require it)
DB_SSLMODE=allow     # Try without SSL first, then with SSL
DB_SSLMODE=prefer     # Try with SSL first, then without (current default)
DB_SSLMODE=require    # Require SSL
```

### Option 3: Connect via SSH Tunnel

If the server only allows local connections, create an SSH tunnel:

```bash
# In WSL, create tunnel
ssh -L 5432:localhost:5432 user@172.18.203.149

# Then in .env, use:
DB_HOST=localhost
```

### Option 4: Check Firewall

The server's firewall might be blocking port 5432:

```bash
# On the server, check if PostgreSQL is listening
sudo netstat -tlnp | grep 5432

# Check firewall rules
sudo ufw status
# If needed, allow PostgreSQL:
sudo ufw allow 5432/tcp
```

## Test Connection

Test the connection from WSL:

```bash
# Try connecting directly
psql -h 172.18.203.149 -U postgres -d inception

# If that works, the Python code should work too
```

## Current Configuration

Your `.env` has:
- `DB_HOST=172.18.203.149`
- `DB_SSLMODE=prefer` (will try SSL first, fallback to no SSL)

If `prefer` doesn't work, try `disable`:
```env
DB_SSLMODE=disable
```

