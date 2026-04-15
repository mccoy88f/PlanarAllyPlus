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

/** Chiave stabile per voci compendio (stesso encoding di `compendium_resource_key` sul server). */
export function compendiumResourceAclKey(compId: string, collectionSlug: string, itemSlug: string): string {
    const json = JSON.stringify([compId, collectionSlug, itemSlug]);
    const bytes = new TextEncoder().encode(json);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]!);
    }
    const b64 = btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    return `compendium:${b64}`;
}
