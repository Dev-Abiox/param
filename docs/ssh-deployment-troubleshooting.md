# SSH Deployment Troubleshooting Guide

## Issue: SSH Authentication Failure During GitHub Actions Deployment

### Problem Description
The GitHub Actions workflow is failing to authenticate with the deployment server, showing:
```
debug1: Authentications that can continue: publickey,password
root@***: Permission denied (publickey,password).
```

This indicates that the SSH key pair is not properly configured between GitHub Actions and the server.

---

## Root Cause
The private SSH key stored in GitHub Secrets (`SSH_PRIVATE_KEY`) does not match the public key in the server's `/root/.ssh/authorized_keys` file, or the server-side SSH configuration has issues.

---

## Solution Steps

### Step 1: Get the Public Key from GitHub Actions

The updated workflow now displays the public key during the "Debug SSH agent and keys" step. Look for the output that says:
```
=== Public Key (add this to server's authorized_keys) ===
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABA... github-actions@clinomic
```

**Copy this entire public key.**

### Step 2: Add Public Key to Server

1. **SSH into your server manually:**
   ```bash
   ssh root@YOUR_SERVER_IP
   ```

2. **Create/edit the authorized_keys file:**
   ```bash
   # Create .ssh directory if it doesn't exist
   mkdir -p ~/.ssh
   
   # Set correct permissions
   chmod 700 ~/.ssh
   
   # Edit authorized_keys
   nano ~/.ssh/authorized_keys
   ```

3. **Add the public key:**
   - Paste the public key from Step 1 on a new line
   - Save and exit (Ctrl+X, then Y, then Enter in nano)

4. **Set correct permissions:**
   ```bash
   chmod 600 ~/.ssh/authorized_keys
   chmod 700 ~/.ssh
   chown -R root:root ~/.ssh
   ```

### Step 3: Verify Server SSH Configuration

1. **Check SSH daemon configuration:**
   ```bash
   sudo nano /etc/ssh/sshd_config
   ```

2. **Ensure these settings are enabled:**
   ```
   PubkeyAuthentication yes
   AuthorizedKeysFile .ssh/authorized_keys
   PermitRootLogin prohibit-password
   ```

3. **Restart SSH service:**
   ```bash
   sudo systemctl restart sshd
   # OR for older systems:
   sudo service ssh restart
   ```

### Step 4: Test SSH Connection Locally

From your local machine (or another trusted machine), test the connection:

```bash
ssh -v root@YOUR_SERVER_IP "echo 'Connection successful'"
```

If this works, GitHub Actions should also work.

---

## Alternative: Generate New SSH Key Pair

If the current keys are problematic, generate a fresh pair:

### On Your Local Machine:

1. **Generate new SSH key pair:**
   ```bash
   ssh-keygen -t rsa -b 4096 -C "github-actions@clinomic" -f ~/.ssh/clinomic_deploy
   ```
   - Press Enter when asked for passphrase (leave empty for GitHub Actions)

2. **Copy the public key to server:**
   ```bash
   ssh-copy-id -i ~/.ssh/clinomic_deploy.pub root@YOUR_SERVER_IP
   ```

3. **Get the private key:**
   ```bash
   cat ~/.ssh/clinomic_deploy
   ```
   - Copy the **entire output** including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`

4. **Update GitHub Secret:**
   - Go to your GitHub repository
   - Navigate to: **Settings → Secrets and variables → Actions**
   - Edit or create `SSH_PRIVATE_KEY`
   - Paste the private key
   - Save

---

## Verification Checklist

Before re-running the GitHub Actions workflow, verify:

- [ ] Public key is in `/root/.ssh/authorized_keys` on the server
- [ ] Permissions: `~/.ssh` is `700`, `authorized_keys` is `600`
- [ ] SSH daemon allows public key authentication
- [ ] GitHub Secret `SSH_PRIVATE_KEY` contains the matching private key
- [ ] GitHub Secret `HOST_IP` contains the correct server IP
- [ ] Server firewall allows SSH connections (port 22)
- [ ] No extra whitespace or line breaks in the GitHub Secret

---

## Testing the Fix

After making changes:

1. **Re-run the GitHub Actions workflow**
2. **Check the "Debug SSH agent and keys" step output:**
   - Should show the loaded key
   - Should display "SSH connection successful"

3. **Check the "Verify SSH Connection Before Deployment" step:**
   - Should pass without errors
   - Should show "SSH Connection Verified"

---

## Common Issues

### Issue: "Too many authentication failures"
**Solution:** Add `IdentitiesOnly yes` to SSH config (already included in updated workflow)

### Issue: "Permission denied" despite correct key
**Solution:** Check server-side file permissions and ownership:
```bash
ls -la ~/.ssh/
# Should show:
# drwx------ 2 root root 4096 ... .ssh
# -rw------- 1 root root  xxx ... authorized_keys
```

### Issue: Server uses non-standard SSH port
**Solution:** Update the workflow to use custom port:
```yaml
ssh -p YOUR_PORT root@${{ secrets.HOST_IP }}
```

---

## Security Notes

1. **Never commit private keys** to the repository
2. **Use GitHub Secrets** for all sensitive data
3. **Rotate SSH keys regularly** (every 90 days recommended)
4. **Consider using** ED25519 keys for better security:
   ```bash
   ssh-keygen -t ed25519 -C "github-actions@clinomic"
   ```
5. **Restrict authorized_keys** with command restrictions if possible
6. **Enable SSH audit logging** on the server for security monitoring

---

## Support

If issues persist after following this guide:

1. **Check GitHub Actions logs** for detailed error messages
2. **Check server SSH logs:**
   ```bash
   sudo tail -f /var/log/auth.log  # Ubuntu/Debian
   # OR
   sudo tail -f /var/log/secure    # CentOS/RHEL
   ```
3. **Verify network connectivity** between GitHub Actions and your server
4. **Ensure server is not blocking** GitHub Actions IP ranges

---

## What Changed in the Workflow

The updated `.github/workflows/production-cicd.yml` now includes:

1. **Enhanced debugging** - Shows loaded SSH keys and fingerprints
2. **Public key display** - Shows exact key to add to server
3. **Better error messages** - Clear instructions when SSH fails
4. **Connection verification** - Tests SSH before deployment
5. **Proper SSH configuration** - Sets correct algorithms and timeouts
6. **File permissions** - Ensures SSH config files have correct permissions

These changes will help identify and fix SSH authentication issues more quickly.
