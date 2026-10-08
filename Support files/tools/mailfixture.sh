#!/bin/sh
# Test-only mail server inside the VM: Dovecot (IMAP, plain, localhost) and
# Postfix (SMTP submission + local delivery to Maildir), plus seeded messages.
# Never part of the image. Run inside the guest:  sh mailfixture.sh
set -eu
apk add -q dovecot postfix seatd-launch
adduser -D alice 2>/dev/null || true
adduser -D craig 2>/dev/null || true
adduser -D bob 2>/dev/null || true
adduser -D jordan 2>/dev/null || true
echo "alice:test" | chpasswd
echo "jordan:test" | chpasswd   # Dovecot refuses uid 0, so the OS uses the "jordan" mailbox

# ---- dovecot: plain IMAP on 127.0.0.1:143, system users, Maildir in $HOME
mkdir -p /etc/dovecot
cat > /etc/dovecot/dovecot.conf <<'EOF'
dovecot_config_version = 2.4.0
dovecot_storage_version = 2.4.0
listen = 127.0.0.1
protocols = imap
ssl = no
auth_allow_cleartext = yes
auth_mechanisms = plain login
mail_driver = maildir
mail_path = ~/Maildir
first_valid_uid = 1000
passdb passwd-file {
  passwd_file_path = /etc/dovecot/users
}
userdb passwd-file {
  passwd_file_path = /etc/dovecot/users
}
namespace inbox {
  inbox = yes
  separator = /
  mailbox Archive {
    auto = subscribe
    special_use = \Archive
  }
  mailbox Trash {
    auto = subscribe
    special_use = \Trash
  }
}
EOF
{ for u in jordan alice craig bob; do printf '%s:{PLAIN}test:%s:%s::/home/%s
%s@localhost:{PLAIN}test:%s:%s::/home/%s
' "$u" "$(id -u $u)" "$(id -g $u)" "$u" "$u" "$(id -u $u)" "$(id -g $u)" "$u"; done; } > /etc/dovecot/users; chmod 644 /etc/dovecot/users
mkdir -p /home/jordan/Maildir /home/alice/Maildir /home/craig/Maildir /home/bob/Maildir; chown -R jordan /home/jordan; chown -R alice /home/alice; chown -R craig /home/craig; chown -R bob /home/bob
doveconf -n >/dev/null || { echo "DOVECOT CONFIG ERROR"; doveconf -n 2>&1 | head -5; exit 1; }
rc-service dovecot restart >/dev/null 2>&1 </dev/null; rc-service dovecot status

# ---- postfix: accept mail on 127.0.0.1:25, deliver locally to ~/Maildir
postconf -e "inet_interfaces = loopback-only" "mydestination = localhost, llmos, localhost.localdomain" \
         "home_mailbox = Maildir/" "myhostname = llmos" "mynetworks = 127.0.0.0/8"
newaliases 2>/dev/null || true
rc-service postfix restart >/dev/null 2>&1 </dev/null; rc-service postfix status
postsuper -d ALL >/dev/null 2>&1 || true
sleep 2

# ---- seed the root inbox with a realistic mix (all to root@localhost)
seed() { # from subject body
    printf 'From: %s\nTo: jordan@localhost\nSubject: %s\nDate: %s\n\n%s\n' "$1" "$2" "$(date -R)" "$3" | sendmail -f "$(echo "$1" | sed 's/.*<//; s/>.*//')" jordan@localhost
}
rm -rf /home/jordan/Maildir/new/* /home/jordan/Maildir/cur/* /home/jordan/Maildir/.Archive /home/jordan/Maildir/.Trash \
       /home/alice/Maildir/new/* /home/alice/Maildir/cur/* 2>/dev/null   # re-runs start from the same six messages
seed "Alice Chen <alice@localhost>" "Dinner on Friday?" "Hi! Are we still on for dinner Friday at 7? Let me know so I can book. -- Alice"
seed "Weekly Digest <digest@newsletter.example>" "Your weekly digest: 10 stories" "Top stories this week... Unsubscribe: http://newsletter.example/u/123"
seed "GitHub <noreply@github.com>" "[repo] Build #4521 succeeded" "Your CI build succeeded. View: https://github.com/example/repo/actions"
seed "Dr. Patel's Office <office@clinic.example>" "Appointment reminder: Tue 10:30" "This is a reminder of your appointment on Tuesday at 10:30. Reply YES to confirm or call 555-0100."
seed "Deals Deals <promo@shop.example>" "50% OFF everything - today only!!!" "Don't miss our biggest sale. Shop now. Unsubscribe here."
seed "Bob Martinez <bob@localhost>" "Invoice for the deck repair" "Hi, attached is the invoice for last week's deck repair, \$850. Can you pay by the 30th? Thanks, Bob"
sleep 3
echo "seeded; jordan inbox: $(ls /home/jordan/Maildir/new | wc -l) messages"
doveadm auth test jordan test 2>&1 | tail -1
echo MAILFIXTURE_OK
