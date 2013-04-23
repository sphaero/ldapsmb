#!/bin/bash
#
# Simple example whiptail script to add a user
#
# This script is not space friendly so if you have spaces in group names
# for example expect the unexpected. I think...

DIR=`dirname $0`

LDAPSMB="$DIR/ldapsmb"

UFIRSTNAME=$(whiptail --inputbox \
        "Enter user's firstname: (With Capitals)" 10 50 \
        --title="Add a new user" 3>&1 1>&2 2>&3)
if [ -z "$UFIRSTNAME" ]; then
    echo "No name entered"
    exit 1
fi

USURNAME=$(whiptail --inputbox \
        "Enter user's surname:" 10 50 \
        --title="Add a new user" 3>&1 1>&2 2>&3)
if [ -z "$USURNAME" ]; then
    echo "No name entered"
    exit 2
fi

#prepare a lowercase from firstname
UFIRSTNAMELOWER=`echo $UFIRSTNAME | tr "[:upper:]" "[:lower:]"`
UNAME=$(whiptail --inputbox \
        "Enter username: (lower case)" 10 50 \
        "$UFIRSTNAMELOWER" \
        --title="Add a new user" 3>&1 1>&2 2>&3)
if [ -z "$UNAME" ]; then
    echo "No username entered"
    exit 3
fi

UMAIL=$(whiptail --inputbox \
        "Enter user's email: (leave empty for local mailbox)" 10 50 \
        --title="Add a new user" 3>&1 1>&2 2>&3)

if whiptail --yesno \
        " Ok, I'm going to add:\n$UFIRSTNAME $USURNAME\n\nwith username:\n$UNAME\n\nDo you wish to proceed?" 15 50 \
        --title="Add a new user"
then $LDAPSMB user -a "$UNAME" -n "$UFIRSTNAME" -N "$USURNAME" -M "$UMAIL" -W -S
else
    echo "Cancelled adding user $UNAME"
    exit 4
fi

if whiptail --yesno \
        "Do you want to add this user to additional groups?" 10 50 \
        --title="Add a new user"
then echo "More groups for user $UNAME"
else
    echo "Finished"
    exit 0
fi

UGROUPS=`getent group | cut -d ":" -f1`
UGROUPLIST=`for G in $UGROUPS; do echo -en "$G $G off "; done`
echo $UGROUPLIST
SELECTED=$(whiptail --checklist \
        "Select groups for $UNAME: (use space to select)" 20 50 13	 \
        $UGROUPLIST \
        --title="Add a new user" 3>&1 1>&2 2>&3)
if [ -z "$SELECTED" ]; then
    echo "No groups selected"
    exit 5
fi
CMD="$LDAPSMB user -m $UNAME"
for GRP in $SELECTED; do
    CMD="$CMD -G $GRP"
done
$CMD
