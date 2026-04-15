/** ACL condiviso per risorse estensioni (allineato a `permission_acl.py` / `resource_acl.py` sul server). */

export interface ExtensionResourceGrant {
    userName: string;
    canView: boolean;
    canEdit: boolean;
}

export interface ExtensionResourceAcl {
    creatorName: string;
    publicView: boolean;
    grants: ExtensionResourceGrant[];
}

export function defaultExtensionResourceAcl(creatorName: string): ExtensionResourceAcl {
    return {
        creatorName,
        publicView: false,
        grants: [],
    };
}

/** Migrazione da un singolo flag ``visibleToPlayers`` / simile. */
export function aclFromLegacyVisibleToPlayers(creatorName: string, visible: boolean): ExtensionResourceAcl {
    return {
        creatorName,
        publicView: visible,
        grants: [],
    };
}

export function effectiveExtensionAccess(
    viewerName: string,
    acl: ExtensionResourceAcl,
): { canView: boolean; canEdit: boolean } {
    if (viewerName === acl.creatorName) {
        return { canView: true, canEdit: true };
    }
    const g = acl.grants.find((x) => x.userName === viewerName);
    if (g) {
        const canView = g.canView || g.canEdit;
        return { canView, canEdit: g.canEdit };
    }
    if (acl.publicView) {
        return { canView: true, canEdit: false };
    }
    return { canView: false, canEdit: false };
}

export function normalizeResourceAcl(acl: ExtensionResourceAcl): ExtensionResourceAcl {
    return {
        creatorName: acl.creatorName.trim(),
        publicView: acl.publicView,
        grants: acl.grants.map((g) => ({
            userName: g.userName.trim(),
            canView: g.canEdit ? true : g.canView,
            canEdit: g.canEdit,
        })),
    };
}

export function resourceAclKey(namespace: string, resourceId: string | number): string {
    return `${namespace}:${resourceId}`;
}
