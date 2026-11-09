-- Protect relationships if an agency membership changes role after assignment.
-- A client user cannot retain agency-staff project assignments, and vice versa.
CREATE FUNCTION public.ensure_role_change_consistency() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.role = 'client_user' AND EXISTS (
     SELECT 1 FROM public.project_members pm
     WHERE pm.agency_id=NEW.agency_id AND pm.user_id=NEW.user_id
  ) THEN
     RAISE EXCEPTION 'Cannot convert assigned staff to client_user';
  END IF;
  IF NEW.role <> 'client_user' AND EXISTS (
     SELECT 1 FROM public.client_memberships cm
     WHERE cm.agency_id=NEW.agency_id AND cm.user_id=NEW.user_id
  ) THEN
     RAISE EXCEPTION 'Cannot convert client contact to agency staff';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER validate_membership_role_change
BEFORE UPDATE OF role ON public.agency_memberships
FOR EACH ROW WHEN (OLD.role IS DISTINCT FROM NEW.role)
EXECUTE FUNCTION public.ensure_role_change_consistency();
