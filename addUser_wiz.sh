#!/bin/bash
#
# Simple example zenity script to add a user
#
# This script is not space friendly so if you have spaces in group names
# for example expect the unexpected. I think...

LDAPSMB="./ldapsmb"

UFIRSTNAME=`zenity --entry \
        --title="Add a new user" \
        --text="Enter user's firstname: (With Capitols)" \
        --entry-text=""`
if [ -z "$UFIRSTNAME" ]; then
    echo "No name entered"
    exit 1
fi

USURNAME=`zenity --entry \
        --title="Add a new user" \
        --text="Enter user's surname:" \
        --entry-text=""`
if [ -z "$USURNAME" ]; then
    echo "No name entered"
    exit 2
fi

#prepare a lowercase from firstname
UFIRSTNAMELOWER=`echo $UFIRSTNAME | tr "[:upper:]" "[:lower:]"`
UNAME=`zenity --entry \
        --title="Add a new user" \
        --text="Enter username: (lower case)" \
        --entry-text="$UFIRSTNAMELOWER"`
if [ -z "$UNAME" ]; then
    echo "No username entered"
    exit 3
fi

UMAIL=`zenity --entry \
        --title="Add a new user" \
        --text="Enter user's email: (leave empty for local mailbox)" \
        --entry-text=""`

if zenity --question \
        --title="Add a new user" \
        --text="Ok, I'm going to add:\n$UFIRSTNAME $USURNAME\n\nwith username:\n$UNAME\n\nDo you wish to proceed?"
then $LDAPSMB user -a $UNAME -n $UFIRSTNAME -N $USURNAME -M $UMAIL -X -S
else 
    echo "Cancelled adding user $UNAME"
    exit 4
fi

if zenity --question \
        --title="Add a new user" \
        --text="Do you want to add this user to additional groups?"
then echo "More groups for user $UNAME"
else 
    echo "Finished"
    exit 0
fi

UGROUPS=`getent group | cut -d ":" -f1 | zenity --list \
        --title="Add a new user" \
        --text="Select groups for $UNAME: (hold CTRL for multi select)" \
        --column="Groups" \
        --multiple --separator=" "`
if [ -z "$UGROUPS" ]; then
    echo "No groups selected"
    exit 5
fi
CMD="$LDAPSMB user -m $UNAME"
for GRP in $UGROUPS; do
    CMD="$CMD -G $GRP"
done
$CMD
