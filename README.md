# pitschi-miscs

To install
```
python3 -m venv venv
source venv/bin/activate
```

Comment out the first line (python-ldap>=3.4.0) if not using ldap
```
pip3 install -r requirements.txt
```

To compare PPMS project users and AD users
```
python3 pitschi-utils.py proj-ad --ad-host ldaps://xxxx --ad-bind xxx@xxxx --ad-pass xxxx --ad-base DC=xx,DC=xx,DC=xx --ppms-url https://xxxx/xxx/ --puma-key xxxx --api2-key xxxx

```

To get PPMS projects, users and their CIs
```
python3 pitschi-utils.py proj-list --ppms-url https://xxxx/xxx/ --puma-key xxxx --api2-key xxxx

```
