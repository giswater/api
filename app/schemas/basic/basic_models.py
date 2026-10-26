"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any, List, Dict, Literal, Union
from ..common import BaseAPIResponse, Body, Data, ExtentModel, UserValue, Form, FormTab, PageInfoReturnModel


# region Input parameters

# endregion

# region Response models


class GetFeatureChangesFeature(BaseModel):
    """Get feature changes feature model"""

    featureClass: str = Field(..., description="Feature class")
    macroSector: int = Field(..., description="Macro sector")
    assetId: Optional[str] = Field(None, description="Asset ID")
    state: Literal[0, 1, 2, 3] = Field(..., description="State")
    exploitation: int = Field(..., description="Exploitation")
    uuid: Optional[str] = Field(None, description="UUID")
    insertAt: Optional[datetime] = Field(None, description="Date of insertion")
    updateAt: Optional[datetime] = Field(None, description="Date of last update")


class GetFeatureChangesArc(GetFeatureChangesFeature):
    """Get feature changes arc model"""

    arcId: int = Field(..., description="Arc ID")


class GetFeatureChangesNode(GetFeatureChangesFeature):
    """Get feature changes node model"""

    nodeId: int = Field(..., description="Node ID")


class GetFeatureChangesConnec(GetFeatureChangesFeature):
    """Get feature changes connec model"""

    connecId: int = Field(..., description="Connec ID")
    customerCode: Optional[str] = Field(None, description="Customer code")


class GetFeatureChangesGully(GetFeatureChangesFeature):
    """Get feature changes gully model"""

    gullyId: int = Field(..., description="Gully ID")


class GetFeatureChangesElement(BaseModel):
    """Get feature changes element model"""

    elementId: int = Field(..., description="Element ID")
    featureClass: str = Field(..., description="Feature class")
    serialNumber: Optional[str] = Field(None, description="Serial number")
    brand: Optional[str] = Field(None, description="Brand")
    model: Optional[str] = Field(None, description="Model")
    descript: Optional[str] = Field(None, description="Description")
    aresepId: Optional[str] = Field(None, description="Aresép ID")


class GetFeatureChangesElementNode(GetFeatureChangesElement):
    """Get feature changes element attached to a node"""

    nodeId: int = Field(..., description="Node ID")


class GetFeatureChangesElementConnec(GetFeatureChangesElement):
    """Get feature changes element attached to a connec"""

    connecId: int = Field(..., description="Connec ID")


class GetFeatureChangesData(BaseModel):
    """Get feature changes data"""

    features: List[
        Union[
            GetFeatureChangesArc,
            GetFeatureChangesNode,
            GetFeatureChangesConnec,
            GetFeatureChangesGully,
            GetFeatureChangesElementNode,
            GetFeatureChangesElementConnec,
            GetFeatureChangesElement,
            GetFeatureChangesFeature,
        ]
    ] = Field(..., description="Features")


class GetFeatureChangesBody(Body[GetFeatureChangesData]):
    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")


class GetFeatureChangesResponse(BaseAPIResponse[GetFeatureChangesBody]):
    pass


class GetInfoFromCoordinatesData(Data):
    """Get info from coordinates data"""

    # NOTE: fields are inherited from Data
    parentFields: List[str] = Field(..., description="Parent fields")


class GetInfoFromCoordinatesBody(Body[GetInfoFromCoordinatesData]):
    pass


class GetInfoFromCoordinatesResponse(BaseAPIResponse[GetInfoFromCoordinatesBody]):
    pass


class GetFeaturesFromPolygonFeatures(BaseModel):
    """Get features from polygon features model"""

    arc: Optional[List[int]] = Field(None, description="Arc IDs")
    node: Optional[List[int]] = Field(None, description="Node IDs")
    connec: Optional[List[int]] = Field(None, description="Connec IDs")
    gully: Optional[List[int]] = Field(None, description="Gully IDs")


class GetFeaturesFromPolygonData(Data):
    """Get features from polygon data"""

    features: GetFeaturesFromPolygonFeatures = Field(..., description="Features")


class GetFeaturesFromPolygonBody(Body[GetFeaturesFromPolygonData]):
    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")


class GetFeaturesFromPolygonResponse(BaseAPIResponse[GetFeaturesFromPolygonBody]):
    pass


class GetSelectorsData(Data):
    """Get selectors data"""

    # NOTE: fields are inherited from Data
    userValues: Optional[List[UserValue]] = Field(None, description="User values")
    geometry: Union[ExtentModel, Dict[str, Any], None] = Field(None, description="Geometry")


class FormStyle(BaseModel):
    """Form style model"""

    rowsColor: Optional[bool] = Field(None, description="Whether the selectors rows are colored or not")


class SelectorFormTab(FormTab):
    """Selector form tab model"""

    tableName: str = Field(..., description="Table name")
    selectorType: str = Field(..., description="Selector type")
    manageAll: bool = Field(..., description="Manage all")
    typeaheadFilter: Optional[str] = Field(None, description="Typeahead filter")
    selectionMode: Optional[str] = Field(None, description="Selection mode")
    typeaheadForced: bool = Field(False, description="Typeahead forced")


class SelectorForm(Form):
    """Selector form model"""

    formTabs: Optional[List[SelectorFormTab]] = Field(None, description="Form tabs")
    style: Optional[FormStyle] = Field(None, description="Form style")


class GetSelectorsBody(Body[GetSelectorsData]):
    form: Optional[SelectorForm] = Field(None, description="Selector form")
    feature: Optional[Dict[str, Any]] = Field(None, description="Feature")


class GetSelectorsResponse(BaseAPIResponse[GetSelectorsBody]):
    pass


class SearchResultValue(BaseModel):
    """Search result value model"""

    key: str = Field(..., description="Key")
    value: Any = Field(..., description="Value")
    displayName: str = Field(..., description="Display name")


class SearchResult(BaseModel):
    """Search result model"""

    section: str = Field(..., description="Section")
    alias: str = Field(..., description="Alias")
    execFunc: Optional[str] = Field(None, description="Exec function")
    tableName: str = Field(..., description="Table name")
    values: Optional[List[SearchResultValue]] = Field(None, description="Values")


class GetSearchData(BaseModel):
    """Get search data"""

    searchResults: List[SearchResult] = Field(..., description="Search results")


class GetSearchBody(Body[GetSearchData]):
    form: None = Field(None, description="Form")
    feature: None = Field(None, description="Feature")


class GetSearchResponse(BaseAPIResponse[GetSearchBody]):
    pass


# region Get arc audit values


class ArcAuditStat(BaseModel):
    """Arc audit stats model"""

    actionType: str = Field(..., description="Action type")
    count: int = Field(..., description="Number of events")


class GetArcAuditValuesData(BaseModel):
    """Get arc audit values data"""

    stats: Optional[Union[List[ArcAuditStat], Dict[str, Any]]] = Field(None, description="Audit stats")
    events: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = Field(None, description="Audit events")


class GetArcAuditValuesBody(Body[GetArcAuditValuesData]):
    form: Optional[Dict] = Field({}, description="Form")
    feature: Optional[Dict] = Field({}, description="Feature")


class GetArcAuditValuesResponse(BaseAPIResponse[GetArcAuditValuesBody]):
    pass


# endregion Get arc audit values


# region Get list


class GetListData(Data):
    """Get list data"""

    type: Optional[str] = Field(None, description="Type of the list")
    fields: Optional[List[Dict]] = Field(None, description="Items of the list")
    addparam: Optional[Dict] = Field(None, description="Additional parameters of the table")
    pageInfo: Optional[PageInfoReturnModel] = Field(None, description="Pagination information")


class ColumnFilterModeOptions(BaseModel):
    """Column filter mode options"""

    filterMode: Optional[str] = Field(None, description="Filter mode")


class DisplayColumnDefOptions(BaseModel):
    """Display column definition options"""

    size: Optional[int] = Field(None, description="Column size")
    enableResizing: Optional[bool] = Field(None, description="Enable column resizing")


class MuiTablePaperProps(BaseModel):
    """Material UI table paper props"""

    elevation: Optional[int] = Field(None, description="Paper elevation")
    sx: Optional[Dict[str, Any]] = Field(None, description="Custom styles")


class MuiTableProps(BaseModel):
    """Material UI table props"""

    sx: Optional[Dict[str, Any]] = Field(None, description="Custom styles")
    size: Optional[Literal["small", "medium"]] = Field(None, description="Table size")


class MuiTableHeadCellProps(BaseModel):
    """Material UI table head cell props"""

    sx: Optional[Dict[str, Any]] = Field(None, description="Custom styles")
    align: Optional[Literal["left", "center", "right"]] = Field(None, description="Cell alignment")


class MuiTableBodyCellProps(BaseModel):
    """Material UI table body cell props"""

    sx: Optional[Dict[str, Any]] = Field(None, description="Custom styles")
    align: Optional[Literal["left", "center", "right"]] = Field(None, description="Cell alignment")


class MuiSearchTextFieldProps(BaseModel):
    """Material UI search text field props"""

    placeholder: Optional[str] = Field(None, description="Search placeholder text")
    variant: Optional[Literal["standard", "outlined", "filled"]] = Field(None, description="Text field variant")


class InitialState(BaseModel):
    """Initial table state"""

    columnVisibility: Optional[Dict[str, bool]] = Field(None, description="Column visibility state")
    density: Optional[Literal["compact", "comfortable", "spacious"]] = Field(None, description="Table density")
    showGlobalFilter: Optional[bool] = Field(None, description="Show global filter")
    sorting: Optional[List[Dict[str, Any]]] = Field(None, description="Initial sorting state")
    pagination: Optional[Dict[str, Any]] = Field(None, description="Initial pagination state")
    columnPinning: Optional[Dict[str, List[str]]] = Field(None, description="Column pinning state")


class GetListTable(BaseModel):
    """Get list table model - Material React Table options"""

    # Core options
    enableColumnActions: Optional[bool] = Field(None, description="Enable column actions menu")
    enableColumnFilters: Optional[bool] = Field(None, description="Enable column filtering")
    enableColumnFilterModes: Optional[bool] = Field(None, description="Enable switching between filter modes")
    enableColumnOrdering: Optional[bool] = Field(None, description="Enable column ordering/reordering")
    enableColumnPinning: Optional[bool] = Field(None, description="Enable column pinning")
    enableColumnResizing: Optional[bool] = Field(None, description="Enable column resizing")
    enableDensityToggle: Optional[bool] = Field(None, description="Enable density toggle")
    enableEditing: Optional[bool] = Field(None, description="Enable editing mode")
    enableExpanding: Optional[bool] = Field(None, description="Enable row expanding")
    enableFacetedValues: Optional[bool] = Field(None, description="Enable faceted values for filters")
    enableFullScreenToggle: Optional[bool] = Field(None, description="Enable full screen toggle")
    enableGlobalFilter: Optional[bool] = Field(None, description="Enable global search filter")
    enableGrouping: Optional[bool] = Field(None, description="Enable row grouping")
    enableHiding: Optional[bool] = Field(None, description="Enable column hiding")
    enableMultiRowSelection: Optional[bool] = Field(None, description="Enable multi-row selection")
    enableMultiSort: Optional[bool] = Field(None, description="Enable multi-column sorting")
    enablePagination: Optional[bool] = Field(None, description="Enable pagination")
    enableRowActions: Optional[bool] = Field(None, description="Enable row actions")
    enableRowNumbers: Optional[bool] = Field(None, description="Enable row numbers")
    enableRowSelection: Optional[bool] = Field(None, description="Enable row selection")
    enableSelectAll: Optional[bool] = Field(None, description="Enable select all checkbox")
    enableSorting: Optional[bool] = Field(None, description="Enable sorting")
    enableStickyHeader: Optional[bool] = Field(None, description="Enable sticky header")
    enableStickyFooter: Optional[bool] = Field(None, description="Enable sticky footer")
    enableTopToolbar: Optional[bool] = Field(None, description="Enable top toolbar")
    enableBottomToolbar: Optional[bool] = Field(None, description="Enable bottom toolbar")

    # Pagination options
    autoResetPageIndex: Optional[bool] = Field(None, description="Auto reset page index")
    paginationDisplayMode: Optional[Literal["default", "pages"]] = Field(None, description="Pagination display mode")
    rowCount: Optional[int] = Field(None, description="Total row count for server-side pagination")

    # Layout options
    columnResizeMode: Optional[Literal["onChange", "onEnd"]] = Field(None, description="Column resize mode")
    columnResizeDirection: Optional[Literal["ltr", "rtl"]] = Field(None, description="Column resize direction")
    layoutMode: Optional[Literal["semantic", "grid"]] = Field(None, description="Table layout mode")

    # Display options
    positionActionsColumn: Optional[Literal["first", "last"]] = Field(None, description="Position of actions column")
    positionExpandColumn: Optional[Literal["first", "last"]] = Field(None, description="Position of expand column")
    positionGlobalFilter: Optional[Literal["left", "right"]] = Field(None, description="Position of global filter")
    positionPagination: Optional[Literal["top", "bottom", "both"]] = Field(None, description="Position of pagination")
    positionToolbarAlertBanner: Optional[Literal["top", "bottom", "none"]] = Field(
        None, description="Position of toolbar alert banner"
    )

    # Behavior options
    editDisplayMode: Optional[Literal["modal", "row", "cell", "table", "custom"]] = Field(
        None, description="Edit display mode"
    )
    selectAllMode: Optional[Literal["all", "page"]] = Field(None, description="Select all mode")
    rowNumberDisplayMode: Optional[Literal["original", "static"]] = Field(None, description="Row number display mode")

    # Styling and customization
    defaultColumn: Optional[Dict[str, Any]] = Field(None, description="Default column options")
    displayColumnDefOptions: Optional[Dict[str, DisplayColumnDefOptions]] = Field(
        None, description="Display column definition options"
    )
    muiTablePaperProps: Optional[Union[MuiTablePaperProps, Dict[str, Any]]] = Field(
        None, description="Material UI table paper props"
    )
    muiTableProps: Optional[Union[MuiTableProps, Dict[str, Any]]] = Field(None, description="Material UI table props")
    muiTableHeadCellProps: Optional[Union[MuiTableHeadCellProps, Dict[str, Any]]] = Field(
        None, description="Material UI table head cell props"
    )
    muiTableBodyCellProps: Optional[Union[MuiTableBodyCellProps, Dict[str, Any]]] = Field(
        None, description="Material UI table body cell props"
    )
    muiSearchTextFieldProps: Optional[Union[MuiSearchTextFieldProps, Dict[str, Any]]] = Field(
        None, description="Material UI search text field props"
    )

    # State management
    initialState: Optional[InitialState] = Field(None, description="Initial table state")

    # Virtualization
    enableRowVirtualization: Optional[bool] = Field(None, description="Enable row virtualization")
    enableColumnVirtualization: Optional[bool] = Field(None, description="Enable column virtualization")

    # Additional configuration
    columnFilterDisplayMode: Optional[Literal["subheader", "popover"]] = Field(
        None, description="Column filter display mode"
    )
    createDisplayMode: Optional[Literal["modal", "row", "custom"]] = Field(None, description="Create display mode")
    manualFiltering: Optional[bool] = Field(None, description="Manual filtering (server-side)")
    manualPagination: Optional[bool] = Field(None, description="Manual pagination (server-side)")
    manualSorting: Optional[bool] = Field(None, description="Manual sorting (server-side)")
    manualGrouping: Optional[bool] = Field(None, description="Manual grouping (server-side)")

    # Localization
    localization: Optional[Dict[str, str]] = Field(None, description="Localization/translation strings")


class GetListHeader(BaseModel):
    """Get list header model"""

    accessorKey: str = Field(..., description="Accessor key")
    editable: Optional[bool] = Field(None, description="Editable")
    enableClickToCopy: Optional[bool] = Field(None, description="Enable click to copy")
    enableColumnFilter: Optional[bool] = Field(None, description="Enable column filter")
    enableColumnOrdering: Optional[bool] = Field(None, description="Enable column ordering")
    enableSorting: Optional[bool] = Field(None, description="Enable sorting")
    filterFn: Optional[str] = Field(None, description="Filter function")
    filterVariant: Optional[str] = Field(None, description="Filter variant")
    header: Optional[str] = Field(None, description="Header")
    size: Optional[int] = Field(None, description="Size")
    sortingFn: Optional[str] = Field(None, description="Sorting function")
    enableColumnActions: Optional[bool] = Field(None, description="Enable column actions")
    columnFilterModeOptions: Optional[bool] = Field(None, description="Column filter mode options")


class GetListForm(BaseModel):
    """Get list form model"""

    table: Optional[GetListTable] = Field(None, description="Table")
    headers: Optional[List[GetListHeader]] = Field(None, description="Headers")


class GetListBody(Body[GetListData]):
    form: GetListForm = Field({}, description="Form")
    feature: Dict = Field({}, description="Feature")


class GetListResponse(BaseAPIResponse[GetListBody]):
    pass


# endregion Get list

# endregion
